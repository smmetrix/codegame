"""Точка входа и главный игровой цикл GreyHat: Python Cyberdeck."""

from __future__ import annotations

import json
import os
import queue
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Final

import customtkinter as ctk
from tkinter import messagebox

from achievements import AchievementManager, AchievementUnlock, AchievementsWindow
from config import (
    ACCENT_CYAN,
    APPEARANCE_MODE,
    APP_NAME,
    APP_VERSION,
    AUTOSAVE_INTERVAL_MS,
    BORDER_COLOR,
    COLOR_THEME,
    DARK_BG,
    DARK_GRAY,
    FONT_HEADING,
    FONT_MONO_FAMILY,
    NEON_GREEN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    UI_SCALE,
    WARNING_RED,
)
from darknet_shop import (
    BRUTEFORCE_TOOLKIT_ID,
    DarkNetShop,
    DarkNetShopWindow,
    PurchaseResult,
    UpgradeNotOwnedError,
)
from game_state import (
    SKILL_LEVELS,
    GameState,
    GameStateError,
    InsufficientFundsError,
    MissionStatus,
)
from minigames import (
    CAMERA_GAME_ID,
    SOCIAL_GAME_ID,
    CameraBypassGame,
    MinigameResult,
    SocialEngineeringGame,
)
from missions_db import (
    MISSION_BY_ID,
    Mission,
    adapt_missions,
    validate_senior_efficiency,
)
from sandbox import Sandbox, SandboxResult, scan_ports
from skill_select import SkillSelectWindow
from ui import CodeEditor, CyberdeckSidebar, MissionPanel, TerminalLevel, TerminalView


SAVE_PATH: Final[Path] = Path(__file__).resolve().parent / "savegame.json"
SAVE_VERSION: Final[int] = 1
_ERROR_LINE_PATTERN: Final[re.Pattern[str]] = re.compile(r"строка\s+(\d+)")

_KARMA_RULES: Final[dict[str, dict[str, int] | int]] = {
    "m01_smart_bulb": {"help": 5, "sell": -5},
    "m02_sensor_types": 2,
    "m04_block_list": 4,
    "m05_password_bruteforce": 5,
    "m06_subnet_scanner": {"help": 10, "sell": -10},
    "m08_contact_cleanup": 4,
    "m09_log_filter": {"help": 15, "sell": -15},
    "m10_caesar_function": 5,
    "m12_md5_cracker": {"notify": 20, "sell": -20},
    "m14_bank_firewall": 15,
    "m15_final_choice": {"help": 50, "sell": -50},
}


class SaveGameError(Exception):
    """Сохранение не может быть прочитано или записано."""


class GreyHatApp(ctk.CTk):
    """Главное окно, связывающее state, Sandbox, missions и весь UI."""

    def __init__(self, *, selected_skill_level: str | None = None) -> None:
        super().__init__()
        self.title(f"{APP_NAME} // v{APP_VERSION}")
        self.geometry("1720x980")
        self.minsize(1240, 760)
        self.configure(fg_color=DARK_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        (
            self.game_state,
            self.achievements,
            self.code_buffers,
            self.completed_minigames,
            self.overclock_used,
            self.paid_hints,
            self.nickname,
            saved_mission_id,
            self._load_warning,
        ) = self._load_savegame()
        if selected_skill_level is not None:
            if selected_skill_level not in SKILL_LEVELS:
                raise ValueError(f"Неизвестный skill level: {selected_skill_level}")
            self.game_state.skill_level = selected_skill_level
        self.missions = adapt_missions(
            self.game_state.skill_level,
            timer_multiplier=self.game_state.get_timer_multiplier(),
        )
        self.mission_by_id = {mission.id: mission for mission in self.missions}
        self.shop = DarkNetShop(self.game_state)
        self.current_mission: Mission | None = None
        self._running = False
        self._closing = False
        self._active_timer_mission_id: str | None = None
        self._trace_failed_missions: set[str] = set()
        self._failed_attempt_counts: dict[str, int] = {}
        self._result_queue: queue.SimpleQueue[tuple[Mission, str, SandboxResult]] = (
            queue.SimpleQueue()
        )
        self._poll_job: str | None = None
        self._autosave_job: str | None = None
        self._shop_window: DarkNetShopWindow | None = None
        self._minigame_menu: Any = None
        self._active_minigame: CameraBypassGame | SocialEngineeringGame | None = None

        self._normalize_mission_progress()
        self._build_interface()
        self.achievements.set_unlock_callback(self._on_achievement_unlock)
        self._populate_missions()
        self._select_initial_mission(saved_mission_id)
        self._refresh_all()
        self._schedule_result_poll()
        self._schedule_autosave()
        self.after(200, self._boot_sequence)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_interface(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_topbar()

        body = ctk.CTkFrame(self, fg_color=DARK_BG, corner_radius=0)
        body.grid(row=1, column=0, padx=10, pady=(4, 10), sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=0, minsize=285)
        body.grid_columnconfigure(1, weight=5, minsize=500)
        body.grid_columnconfigure(2, weight=3, minsize=350)

        self.sidebar = CyberdeckSidebar(
            body,
            nickname=self.nickname,
            on_mission_select=self._select_mission,
            on_trace_expired=self._on_trace_expired,
        )
        self.sidebar.grid(row=0, column=0, padx=(0, 8), sticky="nsew")

        center = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        center.grid(row=0, column=1, padx=4, sticky="nsew")
        center.grid_columnconfigure(0, weight=1)
        center.grid_rowconfigure(0, weight=3)
        center.grid_rowconfigure(1, weight=2)

        self.editor = CodeEditor(
            center,
            on_run=self._run_code,
            on_hint=self._show_hint,
            on_reset=self._reset_code,
            on_save=lambda: self._save_game(show_feedback=True),
            on_change=self._remember_current_code,
        )
        self.editor.grid(row=0, column=0, pady=(0, 6), sticky="nsew")

        self.terminal = TerminalView(
            center,
            command_handler=self._handle_terminal_command,
            typing_delay_ms=7,
            show_timestamps=True,
        )
        self.terminal.grid(row=1, column=0, pady=(6, 0), sticky="nsew")

        self.mission_panel = MissionPanel(
            body,
            on_hint_requested=self._on_hint_revealed,
        )
        self.mission_panel.grid(row=0, column=2, padx=(8, 0), sticky="nsew")

    def _build_topbar(self) -> None:
        topbar = ctk.CTkFrame(
            self,
            height=64,
            fg_color=DARK_GRAY,
            corner_radius=0,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            topbar,
            text="GREYHAT // CYBERDECK OS",
            text_color=NEON_GREEN,
            font=("Inter", 20, "bold"),
        ).grid(row=0, column=0, padx=(18, 12), pady=13, sticky="w")

        self.operation_label = ctk.CTkLabel(
            topbar,
            text="SYSTEM READY",
            text_color=ACCENT_CYAN,
            font=(FONT_MONO_FAMILY, 11, "bold"),
        )
        self.operation_label.grid(row=0, column=1, padx=8)

        actions = ctk.CTkFrame(topbar, fg_color="transparent")
        actions.grid(row=0, column=2, padx=(8, 16), pady=9, sticky="e")

        self.overclock_button = self._topbar_button(
            actions,
            "CPU STEP",
            self._apply_overclock,
            column=0,
            color="#8A5CF5",
        )
        self._topbar_button(
            actions,
            "MINI-GAMES",
            self._open_minigame_menu,
            column=1,
            color=ACCENT_CYAN,
        )
        self._topbar_button(
            actions,
            "DARKNET",
            self._open_shop,
            column=2,
            color=NEON_GREEN,
        )
        self._topbar_button(
            actions,
            "ACHIEVEMENTS",
            self._open_achievements,
            column=3,
            color="#FFD166",
        )
        self._topbar_button(
            actions,
            "SAVE",
            lambda: self._save_game(show_feedback=True),
            column=4,
            color=TEXT_MUTED,
        )

        self.summary_label = ctk.CTkLabel(
            actions,
            text="",
            text_color=TEXT_PRIMARY,
            font=(FONT_MONO_FAMILY, 11, "bold"),
        )
        self.summary_label.grid(row=0, column=5, padx=(12, 0))

    @staticmethod
    def _topbar_button(
        parent: Any,
        text: str,
        command: Any,
        *,
        column: int,
        color: str,
    ) -> Any:
        button = ctk.CTkButton(
            parent,
            text=text,
            width=96,
            height=34,
            fg_color="transparent",
            hover_color="#1D2A33",
            border_width=1,
            border_color=color,
            text_color=color,
            font=("Inter", 10, "bold"),
            command=command,
        )
        button.grid(row=0, column=column, padx=3)
        return button

    # ------------------------------------------------------------------
    # Mission lifecycle and Sandbox
    # ------------------------------------------------------------------

    def _normalize_mission_progress(self) -> None:
        for mission in self.missions:
            if mission.id not in self.game_state.missions:
                self.game_state.set_mission_status(mission.id, MissionStatus.LOCKED)
        if self.game_state.skill_level == "zero":
            for mission in self.missions:
                if (
                    self.game_state.get_mission_status(mission.id)
                    is MissionStatus.LOCKED
                ):
                    self.game_state.set_mission_status(
                        mission.id, MissionStatus.AVAILABLE
                    )
            return
        first = self.missions[0]
        if self.game_state.get_mission_status(first.id) is MissionStatus.LOCKED:
            self.game_state.set_mission_status(first.id, MissionStatus.AVAILABLE)
        for index, mission in enumerate(self.missions[:-1]):
            if (
                self.game_state.get_mission_status(mission.id)
                is MissionStatus.COMPLETED
            ):
                next_id = self.missions[index + 1].id
                if self.game_state.get_mission_status(next_id) is MissionStatus.LOCKED:
                    self.game_state.set_mission_status(next_id, MissionStatus.AVAILABLE)

    def _populate_missions(self) -> None:
        self.sidebar.set_missions(
            self.missions,
            self.game_state.missions,
            selected_id=None,
        )

    def _select_initial_mission(self, saved_mission_id: str | None) -> None:
        if saved_mission_id in self.mission_by_id:
            saved_status = self.game_state.get_mission_status(saved_mission_id)
            if saved_status is not MissionStatus.LOCKED:
                self._select_mission(self.mission_by_id[saved_mission_id])
                return
        for mission in self.missions:
            status = self.game_state.get_mission_status(mission.id)
            if status in {
                MissionStatus.AVAILABLE,
                MissionStatus.IN_PROGRESS,
                MissionStatus.FAILED,
            }:
                self._select_mission(mission)
                return
        self._select_mission(self.missions[-1])

    def _select_mission(self, mission: Mission) -> None:
        if self._running:
            self.terminal.write(
                "Дождитесь завершения текущего Sandbox-процесса.",
                TerminalLevel.WARNING,
                animate=False,
            )
            if self.current_mission is not None:
                self.sidebar.mission_list.set_selected(self.current_mission.id)
            return
        status = self.game_state.get_mission_status(mission.id)
        if status is MissionStatus.LOCKED:
            self.terminal.write_error("Миссия заблокирована предыдущим узлом.")
            return

        if self.current_mission is not None:
            self.code_buffers[self.current_mission.id] = self.editor.get_code()
        if self._active_timer_mission_id != mission.id:
            self.sidebar.trace_meter.reset()
            self._active_timer_mission_id = None

        self.current_mission = mission
        if status in {MissionStatus.AVAILABLE, MissionStatus.FAILED}:
            self.game_state.set_mission_status(mission.id, MissionStatus.IN_PROGRESS)
        self.editor.set_code(
            self.code_buffers.get(mission.id, mission.starter_code), mark_clean=True
        )
        self.mission_panel.set_mission(mission)
        hint_cost = self.game_state.get_hint_cost()
        if self.game_state.skill_level == "senior":
            self.mission_panel.configure_hint_access(enabled=False)
            self.editor.hint_button.configure(text="NO HINTS", state="disabled")
        else:
            displayed_cost = (
                hint_cost if hint_cost > 0 and mission.id not in self.paid_hints else 0
            )
            self.mission_panel.configure_hint_access(
                enabled=True,
                cost=displayed_cost,
            )
            price_text = f" // {displayed_cost} BTC" if displayed_cost else ""
            self.editor.hint_button.configure(
                text=f"ПОДСКАЗКА{price_text}", state="normal"
            )
        self.sidebar.mission_list.set_selected(mission.id)
        self.sidebar.mission_list.update_status(
            mission.id, self.game_state.get_mission_status(mission.id)
        )
        self.operation_label.configure(
            text=f"ACTIVE // {mission.id.upper()}", text_color=ACCENT_CYAN
        )
        self._refresh_overclock_button()
        self._save_game(show_feedback=False)
        if self.game_state.skill_level == "zero":
            self.after(
                450,
                lambda mission_id=mission.id: self._show_auto_hint(mission_id),
            )

    def _show_auto_hint(self, mission_id: str) -> None:
        if (
            self.current_mission is not None
            and self.current_mission.id == mission_id
            and not self.mission_panel.hint_visible
        ):
            self.mission_panel.show_hint()

    def _run_code(self) -> None:
        if self._running or self.current_mission is None:
            return
        source = self.editor.get_code()
        if not source.strip():
            self.terminal.write_error("Редактор пуст.")
            return

        mission = self.current_mission
        self.code_buffers[mission.id] = source
        self._trace_failed_missions.discard(mission.id)
        if mission.time_limit > 0 and self._active_timer_mission_id != mission.id:
            duration = mission.time_limit + self.shop.timer_bonus_seconds
            self.sidebar.trace_meter.set_trace(0.0)
            self.sidebar.trace_meter.start_countdown(duration)
            self._active_timer_mission_id = mission.id
            bonus = self.shop.timer_bonus_seconds
            bonus_text = f" (+{bonus}s VPN)" if bonus else ""
            self.terminal.write_system(
                f"Trace countdown: {duration}s{bonus_text}", animate=False
            )

        self._running = True
        self.editor.set_running(True)
        self.terminal.set_busy(True)
        self.operation_label.configure(text="SANDBOX EXECUTING", text_color=WARNING_RED)
        self.terminal.write(
            f"Запуск {mission.id} в изолированном процессе...",
            TerminalLevel.SYSTEM,
            animate=False,
        )
        worker = threading.Thread(
            target=self._sandbox_worker,
            args=(mission, source),
            daemon=True,
            name=f"Sandbox-{mission.id}",
        )
        worker.start()

    def _sandbox_worker(self, mission: Mission, source: str) -> None:
        sandbox_timeout = 7.0 if mission.tier.value >= 5 else 4.0
        sandbox = Sandbox(
            timeout=sandbox_timeout,
            bonus_api_enabled=self.shop.bruteforce_toolkit_enabled,
        )
        result = sandbox.execute(source)
        self._result_queue.put((mission, source, result))

    def _schedule_result_poll(self) -> None:
        if self._closing:
            return
        self._poll_job = self.after(40, self._poll_results)

    def _poll_results(self) -> None:
        self._poll_job = None
        if self._closing:
            return
        while True:
            try:
                mission, source, result = self._result_queue.get_nowait()
            except queue.Empty:
                break
            self._finish_execution(mission, source, result)
        self._schedule_result_poll()

    def _finish_execution(
        self, mission: Mission, source: str, result: SandboxResult
    ) -> None:
        self._running = False
        self.editor.set_running(False)
        self.terminal.set_busy(False)
        self.operation_label.configure(text="SYSTEM READY", text_color=ACCENT_CYAN)
        self.editor.clear_error_line()

        self.terminal.write_stdout(result.output, animate=False)
        self.terminal.write_stderr(result.stderr, animate=False)
        if mission.id in self._trace_failed_missions:
            self.terminal.write_error(
                "Результат отброшен: Trace Meter достиг критической отметки."
            )
            return
        if not result.success:
            self.terminal.write_error(result.error or "Неизвестная ошибка Sandbox")
            self.sidebar.trace_meter.add_trace(self._trace_penalty(8.0, mission))
            self._highlight_sandbox_error(result.error)
            self._check_trace_limit(mission)
            return

        if self.game_state.skill_level == "senior" and not validate_senior_efficiency(
            mission.id, source
        ):
            self.terminal.write(
                "SENIOR CHECK FAILED // обнаружена очевидная сложность O(n²). "
                "Используйте один линейный проход.",
                TerminalLevel.WARNING,
                animate=False,
            )
            self.sidebar.trace_meter.add_trace(self._trace_penalty(15.0, mission))
            self._check_trace_limit(mission)
            return

        if not mission.validate(result):
            self.terminal.write(
                "Код выполнен, но техническое задание еще не выполнено.",
                TerminalLevel.WARNING,
                animate=False,
            )
            self.sidebar.trace_meter.add_trace(self._trace_penalty(12.0, mission))
            self._check_trace_limit(mission)
            return

        self.terminal.write_success(f"MISSION VERIFIED // {mission.title}")
        self._complete_mission(mission, source, result)

    def _complete_mission(
        self, mission: Mission, source: str, result: SandboxResult
    ) -> None:
        first_completion = (
            self.game_state.get_mission_status(mission.id)
            is not MissionStatus.COMPLETED
        )
        if first_completion:
            karma_delta = self._calculate_karma(mission, result)
            self.game_state.complete_mission(
                mission.id,
                bitcoins_reward=mission.reward_btc,
                exp_reward=mission.reward_exp,
                karma_delta=karma_delta,
            )
            self.game_state.add_item(f"artifact_{mission.id}")
            self.terminal.write(
                f"REWARD // +{mission.reward_btc} BTC +{mission.reward_exp} EXP "
                f"KARMA {karma_delta:+d}",
                TerminalLevel.SUCCESS,
                animate=True,
            )
            self._unlock_next_mission(mission)
        else:
            self.terminal.write_system(
                "Повторная практика завершена; награда не дублируется.", animate=False
            )

        unlocks = self.achievements.record_mission_completion(
            mission.id,
            self.game_state,
            source_code=source,
            sandbox_result=result,
        )
        if unlocks:
            self.terminal.write_system(
                f"Разблокировано достижений: {len(unlocks)}", animate=False
            )
        self.sidebar.trace_meter.set_trace(0.0)
        self.sidebar.trace_meter.stop_countdown()
        self._active_timer_mission_id = None
        self._trace_failed_missions.discard(mission.id)
        self._failed_attempt_counts.pop(mission.id, None)
        self._refresh_all()
        self._save_game(show_feedback=False)

        if mission.id == self.missions[-1].id:
            self._show_finale(result)

    def _unlock_next_mission(self, mission: Mission) -> None:
        index = self.missions.index(mission)
        self.sidebar.mission_list.update_status(mission.id, MissionStatus.COMPLETED)
        if index + 1 >= len(self.missions):
            return
        next_mission = self.missions[index + 1]
        if self.game_state.get_mission_status(next_mission.id) is MissionStatus.LOCKED:
            self.game_state.set_mission_status(next_mission.id, MissionStatus.AVAILABLE)
            self.sidebar.mission_list.update_status(
                next_mission.id, MissionStatus.AVAILABLE
            )
            self.terminal.write(
                f"UNLOCKED // {next_mission.id} // {next_mission.title}",
                TerminalLevel.SYSTEM,
                animate=True,
            )

    @staticmethod
    def _calculate_karma(mission: Mission, result: SandboxResult) -> int:
        rule = _KARMA_RULES.get(mission.id, 0)
        if isinstance(rule, int):
            return rule
        choice = result.variables.get("choice")
        return rule.get(str(choice), 0)

    def _trace_penalty(self, base_penalty: float, mission: Mission) -> float:
        skill_multiplier = {
            "zero": 0.5,
            "beginner": 0.75,
            "practice": 1.0,
            "advanced": 1.5,
            "senior": 2.0,
        }[self.game_state.skill_level]
        adaptive_firewall = 1.0
        if mission.id == "m14_bank_firewall" and self.game_state.skill_level in {
            "advanced",
            "senior",
        }:
            attempts = self._failed_attempt_counts.get(mission.id, 0) + 1
            self._failed_attempt_counts[mission.id] = attempts
            adaptive_firewall += min(0.75, attempts * 0.15)
        return base_penalty * skill_multiplier * adaptive_firewall

    def _highlight_sandbox_error(self, error: str | None) -> None:
        if not error:
            return
        match = _ERROR_LINE_PATTERN.search(error)
        if match is None:
            return
        try:
            self.editor.mark_error_line(int(match.group(1)), error)
        except ValueError:
            return

    def _check_trace_limit(self, mission: Mission) -> None:
        if self.sidebar.trace_meter.value < 100.0:
            return
        self._fail_mission_by_trace(mission)

    def _on_trace_expired(self) -> None:
        if self.current_mission is not None:
            self._fail_mission_by_trace(self.current_mission)

    def _fail_mission_by_trace(self, mission: Mission) -> None:
        if mission.id in self._trace_failed_missions:
            return
        self._trace_failed_missions.add(mission.id)
        self.game_state.set_mission_status(mission.id, MissionStatus.FAILED)
        self.sidebar.mission_list.update_status(mission.id, MissionStatus.FAILED)
        self.operation_label.configure(text="TRACE DETECTED", text_color=WARNING_RED)
        self.terminal.write_error(
            "TRACE LOCKED // операция провалена. Запустите миссию снова для новой попытки."
        )
        self._active_timer_mission_id = None
        self._save_game(show_feedback=False)

    # ------------------------------------------------------------------
    # Hints, shop and upgrades
    # ------------------------------------------------------------------

    def _show_hint(self) -> None:
        if self.current_mission is not None:
            self.mission_panel.show_hint()

    def _on_hint_revealed(self, mission: Mission) -> bool:
        if self.game_state.skill_level == "senior":
            self.terminal.write(
                "SENIOR PROTOCOL // канал подсказок физически отключен.",
                TerminalLevel.WARNING,
                animate=False,
            )
            return False

        hint_cost = self.game_state.get_hint_cost()
        if mission.id not in self.paid_hints and hint_cost > 0:
            try:
                self.game_state.spend_bitcoins(hint_cost)
            except InsufficientFundsError:
                self.terminal.write(
                    f"HINT DENIED // требуется {hint_cost} BTC, доступно "
                    f"{self.game_state.bitcoins} BTC.",
                    TerminalLevel.WARNING,
                    animate=False,
                )
                return False
            self.paid_hints.add(mission.id)
            self.mission_panel.configure_hint_access(enabled=True, cost=0)
            self.editor.hint_button.configure(text="ПОДСКАЗКА")
            self.terminal.write_system(
                f"Hint channel opened for {mission.id}: -{hint_cost} BTC.",
                animate=False,
            )
            self._refresh_all()
            self._save_game(show_feedback=False)
        elif hint_cost == 0:
            self.terminal.write_system(
                f"Hint channel opened for {mission.id}: free.", animate=False
            )

        hint_text = (
            self.shop.copilot_hint(mission)
            if self.shop.copilot_enabled
            else mission.hint
        )
        self.terminal.write(hint_text, TerminalLevel.INFO, animate=True)
        return True

    def _reset_code(self) -> None:
        if self.current_mission is None:
            return
        self.code_buffers.pop(self.current_mission.id, None)
        self.editor.set_code(self.current_mission.starter_code, mark_clean=True)
        self.terminal.write_system("Код сброшен к стартовому шаблону.")

    def _open_shop(self) -> None:
        if self._shop_window is not None and self._shop_window.window.winfo_exists():
            self._shop_window.focus()
            return
        self._shop_window = DarkNetShopWindow(
            self,
            self.shop,
            on_purchase=self._on_shop_purchase,
        )

    def _on_shop_purchase(self, result: PurchaseResult) -> None:
        level = TerminalLevel.SUCCESS if result.success else TerminalLevel.WARNING
        self.terminal.write(result.message, level, animate=True)
        if result.success and result.upgrade.id == BRUTEFORCE_TOOLKIT_ID:
            self.terminal.write_system(
                "BONUS API ONLINE // bruteforce_pin, generate_wordlist, hash_md5, decode_base64"
            )
        self._refresh_all()
        self._save_game(show_feedback=False)

    def _apply_overclock(self) -> None:
        if self.current_mission is None:
            return
        if not self.shop.overclock_enabled:
            self.terminal.write(
                "Overclocked CPU не установлен. Откройте DarkNet.",
                TerminalLevel.WARNING,
                animate=False,
            )
            return
        if self.current_mission.id in self.overclock_used:
            self.terminal.write(
                "CPU STEP уже использован в этой миссии.",
                TerminalLevel.WARNING,
                animate=False,
            )
            return
        try:
            result = self.shop.apply_overclock_step(
                self.current_mission.id, self.editor.get_code()
            )
        except UpgradeNotOwnedError as exc:
            self.terminal.write_error(str(exc))
            return
        if not result.applied:
            self.terminal.write(
                result.explanation, TerminalLevel.WARNING, animate=False
            )
            return
        self.editor.set_code(result.code)
        self.code_buffers[self.current_mission.id] = result.code
        self.overclock_used.add(self.current_mission.id)
        self.terminal.write(
            f"OVERCLOCK PATCH // {result.explanation}",
            TerminalLevel.SUCCESS,
            animate=True,
        )
        self._refresh_overclock_button()
        self._save_game(show_feedback=False)

    def _refresh_overclock_button(self) -> None:
        enabled = (
            self.current_mission is not None
            and self.shop.overclock_enabled
            and self.current_mission.id not in self.overclock_used
        )
        self.overclock_button.configure(state="normal" if enabled else "disabled")

    # ------------------------------------------------------------------
    # Mini-games and achievements
    # ------------------------------------------------------------------

    def _open_minigame_menu(self) -> None:
        if self._minigame_menu is not None and self._minigame_menu.winfo_exists():
            self._minigame_menu.focus_force()
            return
        window = ctk.CTkToplevel(self)
        self._minigame_menu = window
        window.title("Cyberdeck // Mini-games")
        window.geometry("650x480")
        window.minsize(520, 420)
        window.configure(fg_color=DARK_BG)
        window.transient(self)
        window.grab_set()
        window.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            window,
            text="TRAINING SIMULATIONS",
            text_color=ACCENT_CYAN,
            font=("Inter", 22, "bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=22, pady=(20, 5), sticky="ew")
        ctk.CTkLabel(
            window,
            text="Награда за каждую симуляцию выдается один раз.",
            text_color=TEXT_MUTED,
            font=("Inter", 13),
            anchor="w",
        ).grid(row=1, column=0, padx=22, pady=(0, 10), sticky="ew")

        games = (
            (
                CAMERA_GAME_ID,
                "Обход камер наблюдения",
                "Тайминг-кликер: перехватите пять зеленых SAFE FRAME.",
                self._launch_camera_game,
            ),
            (
                SOCIAL_GAME_ID,
                "Социальная инженерия",
                "Диалоговое дерево: получите временный код без постоянного пароля.",
                self._launch_social_game,
            ),
        )
        for row, (game_id, title, description, callback) in enumerate(games, start=2):
            completed = game_id in self.completed_minigames
            card = ctk.CTkFrame(
                window,
                fg_color=DARK_GRAY,
                corner_radius=8,
                border_width=1,
                border_color=NEON_GREEN if completed else BORDER_COLOR,
            )
            card.grid(row=row, column=0, padx=22, pady=8, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                card,
                text=f"{'✓ ' if completed else ''}{title}",
                text_color=NEON_GREEN if completed else TEXT_PRIMARY,
                font=FONT_HEADING,
                anchor="w",
            ).grid(row=0, column=0, padx=14, pady=(12, 3), sticky="ew")
            ctk.CTkLabel(
                card,
                text=description,
                text_color=TEXT_MUTED,
                font=("Inter", 12),
                wraplength=430,
                justify="left",
                anchor="w",
            ).grid(row=1, column=0, padx=14, pady=(0, 12), sticky="ew")
            ctk.CTkButton(
                card,
                text="REPLAY" if completed else "START",
                width=95,
                fg_color="transparent",
                hover_color="#16404B",
                border_width=1,
                border_color=ACCENT_CYAN,
                text_color=ACCENT_CYAN,
                command=callback,
            ).grid(row=0, column=1, rowspan=2, padx=14, pady=14)

    def _launch_camera_game(self) -> None:
        self._close_minigame_menu()
        self._active_minigame = CameraBypassGame(
            self, on_complete=self._on_minigame_complete
        )

    def _launch_social_game(self) -> None:
        self._close_minigame_menu()
        self._active_minigame = SocialEngineeringGame(
            self, on_complete=self._on_minigame_complete
        )

    def _close_minigame_menu(self) -> None:
        if self._minigame_menu is not None and self._minigame_menu.winfo_exists():
            self._minigame_menu.destroy()
        self._minigame_menu = None

    def _on_minigame_complete(self, result: MinigameResult) -> None:
        self.sidebar.trace_meter.add_trace(result.trace_delta)
        if not result.success:
            self.terminal.write(result.details, TerminalLevel.WARNING, animate=True)
            self._save_game(show_feedback=False)
            return
        first_completion = result.game_id not in self.completed_minigames
        if first_completion:
            self.completed_minigames.add(result.game_id)
            self.game_state.add_bitcoins(result.reward_btc)
            self.game_state.add_exp(result.reward_exp)
            self.game_state.add_item(f"minigame_token_{result.game_id}")
            self.achievements.record_minigame_completion(
                result.game_id, self.game_state
            )
            reward = f" +{result.reward_btc} BTC +{result.reward_exp} EXP"
        else:
            reward = " practice run, reward already claimed"
        self.terminal.write(
            f"MINIGAME COMPLETE // score={result.score}{reward}",
            TerminalLevel.SUCCESS,
            animate=True,
        )
        self._refresh_all()
        self._save_game(show_feedback=False)

    def _open_achievements(self) -> None:
        AchievementsWindow(self, self.achievements)

    def _on_achievement_unlock(self, unlock: AchievementUnlock) -> None:
        achievement = unlock.achievement
        if hasattr(self, "terminal"):
            self.terminal.write(
                f"ACHIEVEMENT UNLOCKED // {achievement.title} // "
                f"+{achievement.reward_exp} EXP +{achievement.reward_btc} BTC",
                TerminalLevel.SUCCESS,
                animate=True,
            )

    # ------------------------------------------------------------------
    # Terminal commands
    # ------------------------------------------------------------------

    def _handle_terminal_command(self, raw_command: str) -> str | None:
        parts = raw_command.strip().split()
        if not parts:
            return None
        command = parts[0].lower()
        if command == "help":
            return (
                "help | status | missions | mission <1-15> | run | hint | reset | "
                "trace | scan <host> | shop | overclock | minigames | achievements | save | clear"
            )
        if command == "status":
            return (
                f"rank={self.game_state.rank.value} skill={self.game_state.skill_level} "
                f"exp={self.game_state.exp} btc={self.game_state.bitcoins} "
                f"karma={self.game_state.karma} "
                f"path={self.game_state.karma_path.value} achievements="
                f"{self.achievements.unlocked_count}/5"
            )
        if command == "missions":
            return "\n".join(
                f"{index:02d} {self.game_state.get_mission_status(mission.id).value:11s} "
                f"{mission.title}"
                for index, mission in enumerate(self.missions, start=1)
            )
        if command == "mission" and len(parts) == 2:
            return self._terminal_select_mission(parts[1])
        if command == "run":
            self._run_code()
            return "Sandbox request queued."
        if command == "hint":
            self._show_hint()
            return None
        if command == "reset":
            self._reset_code()
            return None
        if command == "trace":
            return (
                f"detection={self.sidebar.trace_meter.value:.0f}% "
                f"remaining={self.sidebar.trace_meter.remaining_seconds:.1f}s"
            )
        if command == "scan" and len(parts) == 2:
            try:
                ports = scan_ports(parts[1])
            except (TypeError, ValueError) as exc:
                return f"scan error: {exc}"
            return f"simulated ports {parts[1]}: {ports}"
        if command == "shop":
            self._open_shop()
            return "DarkNet window opened."
        if command == "overclock":
            self._apply_overclock()
            return None
        if command == "minigames":
            self._open_minigame_menu()
            return "Training simulations opened."
        if command == "achievements":
            self._open_achievements()
            return "Achievement vault opened."
        if command == "save":
            self._save_game(show_feedback=True)
            return None
        if command == "clear":
            self.terminal.clear()
            return None
        return "Unknown command. Type help."

    def _terminal_select_mission(self, token: str) -> str:
        mission: Mission | None = None
        if token in self.mission_by_id:
            mission = self.mission_by_id[token]
        else:
            try:
                index = int(token) - 1
            except ValueError:
                index = -1
            if 0 <= index < len(self.missions):
                mission = self.missions[index]
        if mission is None:
            return "Mission must be an id or number from 1 to 15."
        if self.game_state.get_mission_status(mission.id) is MissionStatus.LOCKED:
            return "Mission is locked."
        self._select_mission(mission)
        return f"Selected {mission.id}: {mission.title}"

    # ------------------------------------------------------------------
    # Refresh, finale and persistence
    # ------------------------------------------------------------------

    def _remember_current_code(self, code: str) -> None:
        if self.current_mission is not None:
            self.code_buffers[self.current_mission.id] = code

    def _refresh_all(self) -> None:
        self.sidebar.update_player(self.game_state, nickname=self.nickname)
        for mission in self.missions:
            self.sidebar.mission_list.update_status(
                mission.id, self.game_state.get_mission_status(mission.id)
            )
        if self.current_mission is not None:
            self.sidebar.mission_list.set_selected(self.current_mission.id)
        self.summary_label.configure(
            text=(
                f"{self.game_state.skill_level.upper()} // "
                f"{self.game_state.bitcoins} BTC // {self.game_state.exp} EXP // "
                f"ACH {self.achievements.unlocked_count}/5"
            )
        )
        self._refresh_overclock_button()

    def _show_finale(self, result: SandboxResult) -> None:
        choice = result.variables.get("choice")
        if choice == "help":
            title = "WHITE GHOST // ЖЕРТВЫ ПРЕДУПРЕЖДЕНЫ"
            color = ACCENT_CYAN
        elif choice == "sell":
            title = "BLACK GHOST // АРХИВ ПРОДАН"
            color = WARNING_RED
        else:
            title = (
                f"{self.game_state.karma_path.value.upper()} PATH // OPERATION COMPLETE"
            )
            color = NEON_GREEN
        self.terminal.write("=" * 64, TerminalLevel.SYSTEM, animate=False)
        self.terminal.write(title, TerminalLevel.SUCCESS, animate=True)
        self.terminal.write(
            f"FINAL KARMA {self.game_state.karma:+d} // {self.game_state.rank.value}",
            TerminalLevel.INFO,
            animate=True,
        )
        self.operation_label.configure(text="CAMPAIGN COMPLETE", text_color=color)

    def _boot_sequence(self) -> None:
        self.terminal.write_system(
            f"GreyHat Cyberdeck OS v{APP_VERSION} initialized.", animate=True
        )
        self.terminal.write_system(
            f"Operator profile: {self.game_state.skill_level.upper()} // "
            f"timer ×{self.game_state.get_timer_multiplier():g}.",
            animate=True,
        )
        self.terminal.write_system(
            "Sandbox isolation online. Filesystem and real network are blocked.",
            animate=True,
        )
        if self.shop.bruteforce_toolkit_enabled:
            self.terminal.write_system("BruteForce Toolkit bonus API loaded.")
        if self._load_warning:
            self.terminal.write(
                self._load_warning, TerminalLevel.WARNING, animate=False
            )
        self.terminal.write("Type help in terminal.", TerminalLevel.INFO, animate=True)

    def _save_game(self, *, show_feedback: bool) -> None:
        if self.current_mission is not None and hasattr(self, "editor"):
            self.code_buffers[self.current_mission.id] = self.editor.get_code()
        payload = {
            "version": SAVE_VERSION,
            "game_state": self.game_state.to_dict(),
            "achievements": self.achievements.to_dict(),
            "code_buffers": dict(sorted(self.code_buffers.items())),
            "completed_minigames": sorted(self.completed_minigames),
            "overclock_used": sorted(self.overclock_used),
            "paid_hints": sorted(self.paid_hints),
            "nickname": self.nickname,
            "selected_mission_id": (
                self.current_mission.id if self.current_mission is not None else None
            ),
        }
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=SAVE_PATH.parent,
                prefix=".savegame.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                json.dump(payload, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, SAVE_PATH)
        except (OSError, TypeError, ValueError) as exc:
            if temporary_name is not None:
                try:
                    Path(temporary_name).unlink(missing_ok=True)
                except OSError:
                    temporary_name = None
            if hasattr(self, "terminal"):
                self.terminal.write_error(f"SAVE ERROR // {exc}")
            return
        if show_feedback and hasattr(self, "terminal"):
            self.terminal.write_system(f"Saved: {SAVE_PATH.name}", animate=False)

    @classmethod
    def _load_savegame(
        cls,
    ) -> tuple[
        GameState,
        AchievementManager,
        dict[str, str],
        set[str],
        set[str],
        set[str],
        str,
        str | None,
        str | None,
    ]:
        defaults = (
            GameState(),
            AchievementManager(),
            {},
            set(),
            set(),
            set(),
            "ghost",
            None,
            None,
        )
        if not SAVE_PATH.exists():
            return defaults
        try:
            with SAVE_PATH.open("r", encoding="utf-8") as save_file:
                data = json.load(save_file)
            if not isinstance(data, dict):
                raise SaveGameError("Корень savegame должен быть объектом")
            if data.get("version") != SAVE_VERSION:
                raise SaveGameError("Версия savegame не поддерживается")
            game_state_data = data.get("game_state")
            if not isinstance(game_state_data, dict):
                raise SaveGameError("game_state отсутствует")
            game_state = GameState.from_dict(game_state_data)
            achievements_data = data.get("achievements")
            achievements = AchievementManager.from_dict(
                achievements_data if isinstance(achievements_data, dict) else None
            )
            raw_buffers = data.get("code_buffers", {})
            if not isinstance(raw_buffers, dict):
                raise SaveGameError("code_buffers должен быть объектом")
            code_buffers = {
                str(key): str(value)
                for key, value in raw_buffers.items()
                if key in MISSION_BY_ID and isinstance(value, str)
            }
            raw_minigames = data.get("completed_minigames", [])
            raw_overclock = data.get("overclock_used", [])
            raw_paid_hints = data.get("paid_hints", [])
            if (
                not isinstance(raw_minigames, list)
                or not isinstance(raw_overclock, list)
                or not isinstance(raw_paid_hints, list)
            ):
                raise SaveGameError("Некорректный список прогресса")
            completed_minigames = {
                str(item)
                for item in raw_minigames
                if item in {CAMERA_GAME_ID, SOCIAL_GAME_ID}
            }
            overclock_used = {
                str(item) for item in raw_overclock if item in MISSION_BY_ID
            }
            paid_hints = {str(item) for item in raw_paid_hints if item in MISSION_BY_ID}
            nickname = data.get("nickname", "ghost")
            if not isinstance(nickname, str) or not nickname.strip():
                nickname = "ghost"
            selected_id = data.get("selected_mission_id")
            if not isinstance(selected_id, str):
                selected_id = None
            return (
                game_state,
                achievements,
                code_buffers,
                completed_minigames,
                overclock_used,
                paid_hints,
                nickname,
                selected_id,
                None,
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            GameStateError,
            SaveGameError,
            TypeError,
            ValueError,
        ) as exc:
            backup = SAVE_PATH.with_suffix(".broken.json")
            try:
                os.replace(SAVE_PATH, backup)
                location = backup.name
            except OSError:
                location = SAVE_PATH.name
            return (
                GameState(),
                AchievementManager(),
                {},
                set(),
                set(),
                set(),
                "ghost",
                None,
                f"Поврежденное сохранение {location}: {exc}",
            )

    def _schedule_autosave(self) -> None:
        if self._closing:
            return
        self._autosave_job = self.after(AUTOSAVE_INTERVAL_MS, self._autosave)

    def _autosave(self) -> None:
        self._autosave_job = None
        if self._closing:
            return
        self._save_game(show_feedback=False)
        self._schedule_autosave()

    def _on_close(self) -> None:
        if self._running:
            confirmed = messagebox.askyesno(
                "Закрыть Cyberdeck",
                "Sandbox еще выполняет код. Закрыть игру?",
                parent=self,
            )
            if not confirmed:
                return
        self._closing = True
        self._save_game(show_feedback=False)
        for job in (self._poll_job, self._autosave_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    continue
        self.destroy()


def main() -> int:
    ctk.set_appearance_mode(APPEARANCE_MODE)
    ctk.set_default_color_theme(COLOR_THEME)
    ctk.set_widget_scaling(UI_SCALE)

    selected_skill_level: str | None = None
    if not SAVE_PATH.exists():
        selected_skill_level = SkillSelectWindow().run()
        if selected_skill_level is None:
            return 0

    app = GreyHatApp(selected_skill_level=selected_skill_level)
    app.mainloop()
    return 0


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    raise SystemExit(main())
