"""Панели профиля, миссий, обучения и Python Cheat Sheet."""

from __future__ import annotations

import math
import time
import tkinter as tk
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

import customtkinter as ctk

from config import (
    ACCENT_CYAN,
    BORDER_COLOR,
    DARK_BG,
    DARK_GRAY,
    FONT_BODY,
    FONT_MONO_FAMILY,
    FONT_SMALL,
    NEON_GREEN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WARNING_RED,
)
from game_state import GameState, HackerRank, KarmaPath, MissionStatus
from missions_db import Mission, MissionTier, TIER_NAMES


MissionSelectionCallback = Callable[[Mission], None]
HintCallback = Callable[[Mission], bool | None]
TraceExpiredCallback = Callable[[], None]


@dataclass(frozen=True, slots=True)
class _MissionStyle:
    icon: str
    foreground: str
    border: str
    text: str


_MISSION_STYLES: Final[Mapping[MissionStatus, _MissionStyle]] = {
    MissionStatus.LOCKED: _MissionStyle("◆", DARK_BG, BORDER_COLOR, "#59616B"),
    MissionStatus.AVAILABLE: _MissionStyle("▶", "#10232A", ACCENT_CYAN, TEXT_PRIMARY),
    MissionStatus.IN_PROGRESS: _MissionStyle("●", "#12352A", NEON_GREEN, NEON_GREEN),
    MissionStatus.COMPLETED: _MissionStyle("✓", "#101D17", "#245A3A", "#72D99B"),
    MissionStatus.FAILED: _MissionStyle("!", "#35121C", WARNING_RED, WARNING_RED),
}

_RANK_EXP_RANGES: Final[tuple[tuple[int, int, HackerRank], ...]] = (
    (0, 250, HackerRank.SCRIPT_KIDDIE),
    (250, 750, HackerRank.CODE_BREAKER),
    (750, 1_750, HackerRank.NET_RUNNER),
    (1_750, 4_000, HackerRank.GREY_HAT),
    (4_000, 8_000, HackerRank.CYBER_PHANTOM),
    (8_000, 8_000, HackerRank.ZERO_DAY),
)

_CHEAT_SHEET: Final[tuple[tuple[str, str], ...]] = (
    (
        "ПЕРЕМЕННЫЕ И ВЫВОД",
        'name = "ghost"              # str\n'
        "attempts = 3                  # int\n"
        "online = True                # bool\n"
        "print(name, attempts)\n"
        'print(f"User: {name}")',
    ),
    (
        "УСЛОВИЯ",
        "if pin == 7319:\n"
        "    access = True\n"
        "elif attempts > 3:\n"
        "    access = False\n"
        "else:\n"
        "    access = None",
    ),
    (
        "ЦИКЛ FOR",
        "for port in [22, 80, 443]:\n"
        "    print(port)\n\n"
        "for index, value in enumerate(items):\n"
        "    print(index, value)",
    ),
    (
        "ЦИКЛ WHILE",
        "index = 0\n"
        "while index < len(words):\n"
        "    word = words[index]\n"
        "    index += 1\n"
        "    if word == target:\n"
        "        break",
    ),
    (
        "СПИСКИ И СРЕЗЫ",
        "ports = [22, 80, 443, 8080]\n"
        "ports.append(8443)\n"
        "first = ports[0]\n"
        "last = ports[-1]\n"
        "web = ports[1:3]\n"
        "every_second = ports[::2]",
    ),
    (
        "LIST COMPREHENSION",
        "open_ports = [p for p in ports if p > 0]\n"
        'hosts = [f"10.0.0.{n}" for n in range(1, 6)]\n'
        "squares = [n * n for n in range(10)]",
    ),
    (
        "СЛОВАРИ",
        'user = {"name": "mira", "role": "admin"}\n'
        'role = user["role"]\n'
        'count = stats.get("ERROR", 0)\n'
        'stats["ERROR"] = count + 1\n\n'
        "for key, value in user.items():\n"
        "    print(key, value)",
    ),
    (
        "МЕТОДЫ СТРОК",
        "clean = raw.strip().lower()\n"
        'parts = line.split("|", 2)\n'
        'fixed = text.replace("old", "new")\n'
        'text.startswith("ACCESS")\n'
        '"@" in email',
    ),
    (
        "ФУНКЦИИ",
        "def scan_target(host, ports):\n"
        "    found = []\n"
        "    for port in ports:\n"
        "        if port > 0:\n"
        "            found.append(port)\n"
        "    return found\n\n"
        'result = scan_target("localhost", [22, 80])',
    ),
    (
        "ОБРАБОТКА ОШИБОК",
        "try:\n"
        "    port = int(raw_port)\n"
        "except ValueError:\n"
        "    port = 0\n"
        "else:\n"
        '    print("valid")',
    ),
    (
        "BASE64 И MD5",
        "import base64\n"
        'decoded = base64.b64decode(packet).decode("utf-8")\n\n'
        "import hashlib\n"
        'digest = hashlib.md5(text.encode("utf-8")).hexdigest()',
    ),
    (
        "CYBERDECK API",
        'ping("cyberdeck.local")\n'
        'ports = scan_ports("10.0.0.5")\n'
        "receipt = send_payload(target, data)\n"
        "plain = decrypt_caesar(ciphertext, shift)\n\n"
        "# API работает только в офлайн-симуляции.",
    ),
    (
        "ГОРЯЧИЕ КЛАВИШИ",
        "F5 / Ctrl+Enter   запустить код\n"
        "Ctrl+S            сохранить\n"
        "Ctrl+/            комментарий\n"
        "Tab / Shift+Tab   отступ\n"
        "Ctrl+A            выделить все",
    ),
)


class PlayerProfilePanel(ctk.CTkFrame):
    """Карточка профиля с рангом, экономикой и прогрессом EXP."""

    def __init__(
        self,
        master: Any,
        *,
        nickname: str = "ghost",
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", DARK_GRAY)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_COLOR)
        super().__init__(master, **kwargs)

        self._nickname = nickname
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=12, pady=(12, 4), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        self.avatar_label = ctk.CTkLabel(
            header,
            text="GH",
            width=42,
            height=42,
            corner_radius=6,
            fg_color="#0C2D20",
            text_color=NEON_GREEN,
            font=("Inter", 15, "bold"),
        )
        self.avatar_label.grid(row=0, column=0, rowspan=2, padx=(0, 10))

        self.nickname_label = ctk.CTkLabel(
            header,
            text=f"@{nickname}",
            text_color=TEXT_PRIMARY,
            font=("Inter", 15, "bold"),
            anchor="w",
        )
        self.nickname_label.grid(row=0, column=1, sticky="sw")

        self.rank_label = ctk.CTkLabel(
            header,
            text="Script Kiddie",
            text_color=ACCENT_CYAN,
            font=FONT_SMALL,
            anchor="w",
        )
        self.rank_label.grid(row=1, column=1, sticky="nw")

        divider = ctk.CTkFrame(self, height=1, fg_color=BORDER_COLOR)
        divider.grid(row=1, column=0, padx=12, pady=5, sticky="ew")

        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.grid(row=2, column=0, padx=12, pady=4, sticky="ew")
        stats.grid_columnconfigure((0, 1), weight=1)

        self.exp_label = self._create_stat(stats, "EXP", "0", 0, 0, ACCENT_CYAN)
        self.balance_label = self._create_stat(
            stats, "WALLET", "0 BTC", 0, 1, NEON_GREEN
        )
        self.karma_label = self._create_stat(
            stats, "KARMA", "0 // GREY", 1, 0, TEXT_MUTED, columnspan=2
        )

        self.exp_progress = ctk.CTkProgressBar(
            self,
            height=6,
            fg_color=DARK_BG,
            progress_color=ACCENT_CYAN,
            border_width=0,
        )
        self.exp_progress.grid(row=3, column=0, padx=12, pady=(4, 12), sticky="ew")
        self.exp_progress.set(0.0)

    @staticmethod
    def _create_stat(
        parent: Any,
        title: str,
        value: str,
        row: int,
        column: int,
        color: str,
        *,
        columnspan: int = 1,
    ) -> Any:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            padx=3,
            pady=3,
            sticky="ew",
        )
        ctk.CTkLabel(
            frame,
            text=title,
            text_color=TEXT_MUTED,
            font=("Inter", 9),
            anchor="w",
        ).pack(fill="x")
        label = ctk.CTkLabel(
            frame,
            text=value,
            text_color=color,
            font=(FONT_MONO_FAMILY, 12, "bold"),
            anchor="w",
        )
        label.pack(fill="x")
        return label

    def update_profile(
        self,
        *,
        nickname: str,
        rank: HackerRank | str,
        exp: int,
        balance_btc: int,
        karma: int,
        karma_path: KarmaPath | str,
    ) -> None:
        if not nickname.strip():
            raise ValueError("nickname не может быть пустым")
        for value, name in (
            (exp, "exp"),
            (balance_btc, "balance_btc"),
            (karma, "karma"),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} должен быть целым числом")
        if exp < 0 or balance_btc < 0:
            raise ValueError("EXP и BTC не могут быть отрицательными")

        rank_text = rank.value if isinstance(rank, HackerRank) else str(rank)
        path_text = (
            karma_path.value if isinstance(karma_path, KarmaPath) else str(karma_path)
        )
        path_normalized = path_text.lower()
        if "бел" in path_normalized or "white" in path_normalized:
            karma_color = ACCENT_CYAN
        elif "чер" in path_normalized or "black" in path_normalized:
            karma_color = WARNING_RED
        else:
            karma_color = TEXT_MUTED

        self._nickname = nickname
        self.nickname_label.configure(text=f"@{nickname}")
        self.rank_label.configure(text=rank_text)
        self.exp_label.configure(text=f"{exp:,}".replace(",", " "))
        self.balance_label.configure(text=f"{balance_btc:,} BTC".replace(",", " "))
        self.karma_label.configure(
            text=f"{karma:+d} // {path_text.upper()}", text_color=karma_color
        )
        self.exp_progress.set(self._rank_progress(exp, rank_text))

    def update_from_state(self, state: GameState, *, nickname: str = "ghost") -> None:
        self.update_profile(
            nickname=nickname,
            rank=state.rank,
            exp=state.exp,
            balance_btc=state.bitcoins,
            karma=state.karma,
            karma_path=state.karma_path,
        )

    @staticmethod
    def _rank_progress(exp: int, rank_text: str) -> float:
        for start, end, rank in _RANK_EXP_RANGES:
            if rank.value == rank_text:
                if end == start:
                    return 1.0
                return max(0.0, min(1.0, (exp - start) / (end - start)))
        return 0.0


class TraceMeter(ctk.CTkFrame):
    """Индикатор обнаружения с countdown и красной blink animation."""

    def __init__(
        self,
        master: Any,
        *,
        danger_threshold: float = 70.0,
        on_expired: TraceExpiredCallback | None = None,
        **kwargs: Any,
    ) -> None:
        if not 1.0 <= danger_threshold <= 100.0:
            raise ValueError("danger_threshold должен быть от 1 до 100")
        kwargs.setdefault("fg_color", DARK_GRAY)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_COLOR)
        super().__init__(master, **kwargs)

        self._danger_threshold = danger_threshold
        self._on_expired = on_expired
        self._trace_value = 0.0
        self._deadline: float | None = None
        self._timer_duration = 0.0
        self._timer_job: str | None = None
        self._blink_job: str | None = None
        self._blink_on = False
        self._expired_notified = False
        self._destroyed = False

        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=12, pady=(10, 2), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="TRACE METER",
            text_color=TEXT_MUTED,
            font=("Inter", 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.status_label = ctk.CTkLabel(
            header,
            text="STEALTH",
            text_color=NEON_GREEN,
            font=(FONT_MONO_FAMILY, 10, "bold"),
            anchor="e",
        )
        self.status_label.grid(row=0, column=1, sticky="e")

        self.progress = ctk.CTkProgressBar(
            self,
            height=12,
            corner_radius=4,
            fg_color=DARK_BG,
            progress_color=NEON_GREEN,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        self.progress.grid(row=1, column=0, padx=12, pady=5, sticky="ew")
        self.progress.set(0.0)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, padx=12, pady=(1, 9), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.value_label = ctk.CTkLabel(
            footer,
            text="DETECTION 0%",
            text_color=TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 10),
            anchor="w",
        )
        self.value_label.grid(row=0, column=0, sticky="w")
        self.timer_label = ctk.CTkLabel(
            footer,
            text="NO TIMER",
            text_color=TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 10),
            anchor="e",
        )
        self.timer_label.grid(row=0, column=1, sticky="e")

    @property
    def value(self) -> float:
        return self._trace_value

    @property
    def remaining_seconds(self) -> float:
        if self._deadline is None:
            return 0.0
        return max(0.0, self._deadline - time.monotonic())

    def set_trace(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Trace value должен быть числом")
        self._trace_value = max(0.0, min(100.0, float(value)))
        self.progress.set(self._trace_value / 100.0)
        self.value_label.configure(text=f"DETECTION {self._trace_value:.0f}%")
        self._refresh_danger_state()

    def add_trace(self, delta: float) -> float:
        if isinstance(delta, bool) or not isinstance(delta, (int, float)):
            raise TypeError("Trace delta должен быть числом")
        self.set_trace(self._trace_value + float(delta))
        return self._trace_value

    def start_countdown(
        self,
        seconds: int | float,
        *,
        on_expired: TraceExpiredCallback | None = None,
    ) -> None:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise TypeError("seconds должен быть числом")
        if seconds < 0:
            raise ValueError("seconds не может быть отрицательным")
        self.stop_countdown(clear_label=False)
        if on_expired is not None:
            self._on_expired = on_expired
        if seconds == 0:
            self._deadline = None
            self._timer_duration = 0.0
            self.timer_label.configure(text="NO TIMER", text_color=TEXT_MUTED)
            self._refresh_danger_state()
            return

        self._timer_duration = float(seconds)
        self._deadline = time.monotonic() + self._timer_duration
        self._expired_notified = False
        self._update_countdown()

    def stop_countdown(self, *, clear_label: bool = True) -> None:
        if self._timer_job is not None:
            self.after_cancel(self._timer_job)
            self._timer_job = None
        self._deadline = None
        self._timer_duration = 0.0
        self.progress.set(self._trace_value / 100.0)
        if clear_label:
            self.timer_label.configure(text="NO TIMER", text_color=TEXT_MUTED)
        self._refresh_danger_state()

    def reset(self) -> None:
        self.stop_countdown()
        self.set_trace(0.0)
        self._expired_notified = False

    def _update_countdown(self) -> None:
        self._timer_job = None
        if self._destroyed or self._deadline is None:
            return
        remaining = self.remaining_seconds
        seconds_ceil = math.ceil(remaining)
        minutes, seconds = divmod(seconds_ceil, 60)
        self.timer_label.configure(text=f"T-{minutes:02d}:{seconds:02d}")

        if self._timer_duration > 0:
            elapsed_ratio = 1.0 - remaining / self._timer_duration
            countdown_trace = min(100.0, max(self._trace_value, elapsed_ratio * 100.0))
            self.progress.set(countdown_trace / 100.0)

        if remaining <= 0:
            self.timer_label.configure(text="TRACE LOCKED", text_color=WARNING_RED)
            self.set_trace(100.0)
            if not self._expired_notified:
                self._expired_notified = True
                if self._on_expired is not None:
                    self._on_expired()
            return

        self._refresh_danger_state()
        self._timer_job = self.after(100, self._update_countdown)

    def _is_danger(self) -> bool:
        timer_danger = self._deadline is not None and self.remaining_seconds <= 10.0
        return self._trace_value >= self._danger_threshold or timer_danger

    def _refresh_danger_state(self) -> None:
        if self._is_danger():
            self.status_label.configure(text="DANGER", text_color=WARNING_RED)
            self.value_label.configure(text_color=WARNING_RED)
            self.timer_label.configure(text_color=WARNING_RED)
            if self._blink_job is None:
                self._blink()
        else:
            self._stop_blink()
            self.status_label.configure(text="STEALTH", text_color=NEON_GREEN)
            self.value_label.configure(text_color=TEXT_MUTED)
            if self._deadline is not None:
                self.timer_label.configure(text_color=ACCENT_CYAN)
            self.progress.configure(progress_color=NEON_GREEN)
            self.configure(border_color=BORDER_COLOR)

    def _blink(self) -> None:
        self._blink_job = None
        if self._destroyed or not self._is_danger():
            self._stop_blink()
            return
        self._blink_on = not self._blink_on
        active_color = WARNING_RED if self._blink_on else "#7A1C34"
        self.progress.configure(progress_color=active_color)
        self.configure(border_color=active_color)
        self._blink_job = self.after(320, self._blink)

    def _stop_blink(self) -> None:
        if self._blink_job is not None:
            self.after_cancel(self._blink_job)
            self._blink_job = None
        self._blink_on = False

    def destroy(self) -> None:
        self._destroyed = True
        for job in (self._timer_job, self._blink_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    continue
        super().destroy()


class MissionListPanel(ctk.CTkFrame):
    """Адаптивный список миссий, сгруппированный по пяти tiers."""

    def __init__(
        self,
        master: Any,
        *,
        on_select: MissionSelectionCallback | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", DARK_GRAY)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_COLOR)
        super().__init__(master, **kwargs)

        self._on_select = on_select
        self._missions: dict[str, Mission] = {}
        self._statuses: dict[str, MissionStatus] = {}
        self._buttons: dict[str, Any] = {}
        self._selected_id: str | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=12, pady=(10, 3), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="MISSION NETWORK",
            text_color=ACCENT_CYAN,
            font=("Inter", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.counter_label = ctk.CTkLabel(
            header,
            text="0 / 0",
            text_color=TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 10),
            anchor="e",
        )
        self.counter_label.grid(row=0, column=1, sticky="e")

        self.progress = ctk.CTkProgressBar(
            self,
            height=5,
            fg_color=DARK_BG,
            progress_color=NEON_GREEN,
        )
        self.progress.grid(row=1, column=0, padx=12, pady=(2, 6), sticky="ew")
        self.progress.set(0.0)

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=ACCENT_CYAN,
        )
        self.scroll.grid(row=2, column=0, padx=5, pady=(0, 6), sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

    def set_missions(
        self,
        missions: Iterable[Mission],
        statuses: Mapping[str, MissionStatus | str] | None = None,
        *,
        selected_id: str | None = None,
    ) -> None:
        mission_list = list(missions)
        if len({mission.id for mission in mission_list}) != len(mission_list):
            raise ValueError("Mission ids должны быть уникальными")
        if selected_id is not None and selected_id not in {m.id for m in mission_list}:
            raise KeyError(f"Неизвестная выбранная миссия: {selected_id}")

        for child in self.scroll.winfo_children():
            child.destroy()
        self._missions = {mission.id: mission for mission in mission_list}
        self._statuses = {}
        self._buttons = {}
        self._selected_id = selected_id

        current_tier: MissionTier | None = None
        row = 0
        for mission in mission_list:
            if mission.tier is not current_tier:
                current_tier = mission.tier
                ctk.CTkLabel(
                    self.scroll,
                    text=f"TIER {int(current_tier)} // {TIER_NAMES[current_tier].upper()}",
                    text_color=TEXT_MUTED,
                    font=(FONT_MONO_FAMILY, 9, "bold"),
                    anchor="w",
                ).grid(row=row, column=0, padx=8, pady=(10, 2), sticky="ew")
                row += 1

            raw_status: MissionStatus | str = MissionStatus.LOCKED
            if statuses is not None:
                raw_status = statuses.get(mission.id, MissionStatus.LOCKED)
            status = (
                raw_status
                if isinstance(raw_status, MissionStatus)
                else MissionStatus(raw_status)
            )
            self._statuses[mission.id] = status

            button = ctk.CTkButton(
                self.scroll,
                text="",
                height=44,
                anchor="w",
                font=("Inter", 11),
                border_width=1,
                command=lambda mission_id=mission.id: self._select(mission_id),
            )
            button.grid(row=row, column=0, padx=3, pady=3, sticky="ew")
            self._buttons[mission.id] = button
            self._render_button(mission.id)
            row += 1

        self._refresh_progress()

    def _select(self, mission_id: str) -> None:
        status = self._statuses[mission_id]
        if status is MissionStatus.LOCKED:
            return
        self.set_selected(mission_id)
        if self._on_select is not None:
            self._on_select(self._missions[mission_id])

    def set_selected(self, mission_id: str | None) -> None:
        if mission_id is not None and mission_id not in self._missions:
            raise KeyError(f"Неизвестная миссия: {mission_id}")
        previous = self._selected_id
        self._selected_id = mission_id
        if previous is not None and previous in self._buttons:
            self._render_button(previous)
        if mission_id is not None:
            self._render_button(mission_id)

    def update_status(
        self, mission_id: str, status: MissionStatus | str
    ) -> MissionStatus:
        if mission_id not in self._missions:
            raise KeyError(f"Неизвестная миссия: {mission_id}")
        normalized = (
            status if isinstance(status, MissionStatus) else MissionStatus(status)
        )
        self._statuses[mission_id] = normalized
        self._render_button(mission_id)
        self._refresh_progress()
        return normalized

    def _render_button(self, mission_id: str) -> None:
        mission = self._missions[mission_id]
        status = self._statuses[mission_id]
        style = _MISSION_STYLES[status]
        selected = mission_id == self._selected_id
        foreground = "#153A2C" if selected else style.foreground
        border = NEON_GREEN if selected else style.border
        text_color = NEON_GREEN if selected else style.text
        timer = "∞" if mission.time_limit == 0 else f"{mission.time_limit}s"
        self._buttons[mission_id].configure(
            text=f"{style.icon}  {mission.id[:3].upper()}  {mission.title}\n     {timer}  +{mission.reward_exp} EXP",
            fg_color=foreground,
            hover_color="#173B31" if status is not MissionStatus.LOCKED else DARK_BG,
            border_color=border,
            text_color=text_color,
            state="disabled" if status is MissionStatus.LOCKED else "normal",
        )

    def _refresh_progress(self) -> None:
        total = len(self._missions)
        completed = sum(
            status is MissionStatus.COMPLETED for status in self._statuses.values()
        )
        self.counter_label.configure(text=f"{completed} / {total}")
        self.progress.set(completed / total if total else 0.0)

    def set_selection_callback(self, callback: MissionSelectionCallback | None) -> None:
        self._on_select = callback


class CyberdeckSidebar(ctk.CTkFrame):
    """Готовая левая колонка: профиль, Trace Meter и mission network."""

    def __init__(
        self,
        master: Any,
        *,
        nickname: str = "ghost",
        on_mission_select: MissionSelectionCallback | None = None,
        on_trace_expired: TraceExpiredCallback | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.profile = PlayerProfilePanel(self, nickname=nickname)
        self.profile.grid(row=0, column=0, pady=(0, 8), sticky="ew")

        self.trace_meter = TraceMeter(self, on_expired=on_trace_expired)
        self.trace_meter.grid(row=1, column=0, pady=(0, 8), sticky="ew")

        self.mission_list = MissionListPanel(self, on_select=on_mission_select)
        self.mission_list.grid(row=2, column=0, sticky="nsew")

    def update_player(self, state: GameState, *, nickname: str = "ghost") -> None:
        self.profile.update_from_state(state, nickname=nickname)

    def set_missions(
        self,
        missions: Iterable[Mission],
        statuses: Mapping[str, MissionStatus | str],
        *,
        selected_id: str | None = None,
    ) -> None:
        self.mission_list.set_missions(missions, statuses, selected_id=selected_id)


class MissionBriefPanel(ctk.CTkScrollableFrame):
    """Брифинг, теория, награды, карма и раскрываемая подсказка."""

    def __init__(
        self,
        master: Any,
        *,
        on_hint_requested: HintCallback | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("corner_radius", 0)
        kwargs.setdefault("scrollbar_button_color", BORDER_COLOR)
        kwargs.setdefault("scrollbar_button_hover_color", ACCENT_CYAN)
        super().__init__(master, **kwargs)

        self._mission: Mission | None = None
        self._on_hint_requested = on_hint_requested
        self._hint_visible = False
        self.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self,
            text="ВЫБЕРИТЕ МИССИЮ",
            text_color=TEXT_PRIMARY,
            font=("Inter", 19, "bold"),
            anchor="w",
        )
        self.title_label.grid(row=0, column=0, padx=8, pady=(8, 2), sticky="ew")

        self.meta_label = ctk.CTkLabel(
            self,
            text="",
            text_color=ACCENT_CYAN,
            font=(FONT_MONO_FAMILY, 10, "bold"),
            anchor="w",
        )
        self.meta_label.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")

        self.description_box = self._create_readonly_section(
            row=2,
            title="MISSION BRIEF // СЮЖЕТ И ТЗ",
            height=190,
            color=TEXT_PRIMARY,
        )
        self.tutorial_box = self._create_readonly_section(
            row=3,
            title="ACADEMY // ОБЪЯСНЕНИЕ PYTHON",
            height=245,
            color="#C8D5E1",
        )
        self.karma_box = self._create_readonly_section(
            row=4,
            title="MORAL ROUTE // ПОСЛЕДСТВИЯ",
            height=105,
            color="#FFD166",
        )

        hint_frame = ctk.CTkFrame(
            self,
            fg_color="#0C141B",
            corner_radius=6,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        hint_frame.grid(row=5, column=0, padx=8, pady=(8, 14), sticky="ew")
        hint_frame.grid_columnconfigure(0, weight=1)
        self.hint_label = ctk.CTkLabel(
            hint_frame,
            text="Подсказка скрыта. Сначала попробуйте решить задачу самостоятельно.",
            wraplength=360,
            justify="left",
            anchor="w",
            text_color=TEXT_MUTED,
            font=FONT_SMALL,
        )
        self.hint_label.grid(row=0, column=0, padx=12, pady=10, sticky="ew")
        self._hint_button_text = "ПОКАЗАТЬ ПОДСКАЗКУ"
        self.hint_button = ctk.CTkButton(
            hint_frame,
            text=self._hint_button_text,
            width=160,
            height=30,
            fg_color="transparent",
            hover_color="#12343B",
            border_width=1,
            border_color=ACCENT_CYAN,
            text_color=ACCENT_CYAN,
            command=self.toggle_hint,
        )
        self.hint_button.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")

    def _create_readonly_section(
        self,
        *,
        row: int,
        title: str,
        height: int,
        color: str,
    ) -> Any:
        frame = ctk.CTkFrame(
            self,
            fg_color="#0C1118",
            corner_radius=6,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        frame.grid(row=row, column=0, padx=8, pady=5, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame,
            text=title,
            text_color=NEON_GREEN,
            font=(FONT_MONO_FAMILY, 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="ew")
        textbox = ctk.CTkTextbox(
            frame,
            height=height,
            wrap="word",
            activate_scrollbars=True,
            fg_color="transparent",
            text_color=color,
            font=FONT_BODY,
            border_width=0,
        )
        textbox.grid(row=1, column=0, padx=5, pady=(2, 7), sticky="ew")
        textbox.configure(state="disabled")
        return textbox

    def set_mission(self, mission: Mission) -> None:
        if not isinstance(mission, Mission):
            raise TypeError("mission должен быть экземпляром Mission")
        self._mission = mission
        timer = (
            "без таймера" if mission.time_limit == 0 else f"{mission.time_limit} сек"
        )
        self.title_label.configure(text=mission.title)
        self.meta_label.configure(
            text=(
                f"TIER {int(mission.tier)} // {TIER_NAMES[mission.tier].upper()}  "
                f"|  +{mission.reward_exp} EXP  +{mission.reward_btc} BTC  |  {timer}"
            )
        )
        self._set_text(self.description_box, mission.description)
        tutorial_container = self.tutorial_box.master
        if mission.tutorial_text:
            tutorial_container.grid()
            self._set_text(self.tutorial_box, mission.tutorial_text)
        else:
            tutorial_container.grid_remove()
        self._set_text(self.karma_box, mission.karma_choice)
        self.hide_hint()

    @staticmethod
    def _set_text(textbox: Any, text: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")
        textbox.yview_moveto(0.0)

    def configure_hint_access(self, *, enabled: bool, cost: int = 0) -> None:
        if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
            raise ValueError("cost должен быть неотрицательным целым числом")
        if enabled:
            suffix = f" // {cost} BTC" if cost else ""
            self._hint_button_text = f"ПОКАЗАТЬ ПОДСКАЗКУ{suffix}"
            self.hint_button.configure(state="normal")
        else:
            self._hint_button_text = "ПОДСКАЗКИ ОТКЛЮЧЕНЫ"
            self.hint_button.configure(state="disabled")
        if not self._hint_visible:
            self.hint_button.configure(text=self._hint_button_text)

    def toggle_hint(self) -> None:
        if self._mission is None:
            return
        if self._hint_visible:
            self.hide_hint()
            return
        if self._on_hint_requested is not None:
            allowed = self._on_hint_requested(self._mission)
            if allowed is False:
                return
        self._hint_visible = True
        self.hint_label.configure(text=self._mission.hint, text_color=ACCENT_CYAN)
        self.hint_button.configure(text="СКРЫТЬ ПОДСКАЗКУ")

    def hide_hint(self) -> None:
        self._hint_visible = False
        self.hint_label.configure(
            text="Подсказка скрыта. Сначала попробуйте решить задачу самостоятельно.",
            text_color=TEXT_MUTED,
        )
        self.hint_button.configure(text=self._hint_button_text)

    @property
    def current_mission(self) -> Mission | None:
        return self._mission

    @property
    def hint_visible(self) -> bool:
        return self._hint_visible


class CheatSheetPanel(ctk.CTkFrame):
    """Поисковая шпаргалка по синтаксису, методам и Cyberdeck API."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("corner_radius", 0)
        super().__init__(master, **kwargs)

        self._cards: list[tuple[str, str, Any]] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.grid(row=0, column=0, padx=6, pady=(7, 3), sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)
        self.search_entry = ctk.CTkEntry(
            search_frame,
            height=32,
            placeholder_text="Поиск: циклы, строки, словари...",
            fg_color=DARK_BG,
            border_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_entry.bind("<KeyRelease>", self._filter_cards)
        ctk.CTkButton(
            search_frame,
            text="×",
            width=34,
            height=32,
            fg_color="transparent",
            hover_color="#2B1820",
            border_width=1,
            border_color=BORDER_COLOR,
            text_color=TEXT_MUTED,
            command=self.clear_search,
        ).grid(row=0, column=1, padx=(5, 0))

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=ACCENT_CYAN,
        )
        self.scroll.grid(row=1, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)
        self._build_cards()

    def _build_cards(self) -> None:
        for row, (title, code) in enumerate(_CHEAT_SHEET):
            card = ctk.CTkFrame(
                self.scroll,
                fg_color="#0C1118",
                corner_radius=6,
                border_width=1,
                border_color=BORDER_COLOR,
            )
            card.grid(row=row, column=0, padx=4, pady=5, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                card,
                text=title,
                text_color=ACCENT_CYAN,
                font=(FONT_MONO_FAMILY, 10, "bold"),
                anchor="w",
            ).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="ew")
            ctk.CTkLabel(
                card,
                text=code,
                text_color="#C8D5E1",
                font=(FONT_MONO_FAMILY, 11),
                justify="left",
                anchor="w",
            ).grid(row=1, column=0, padx=10, pady=(2, 9), sticky="ew")
            self._cards.append((title.lower(), code.lower(), card))

    def _filter_cards(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        query = self.search_entry.get().strip().lower()
        visible_row = 0
        for title, code, card in self._cards:
            if not query or query in title or query in code:
                card.grid(row=visible_row, column=0, padx=4, pady=5, sticky="ew")
                visible_row += 1
            else:
                card.grid_remove()

    def set_search(self, query: str) -> None:
        if not isinstance(query, str):
            raise TypeError("query должен быть строкой")
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, query)
        self._filter_cards()

    def clear_search(self) -> None:
        self.set_search("")
        self.search_entry.focus_set()


class MissionPanel(ctk.CTkFrame):
    """Правая info-panel с tabs «Бриф & Обучение» и «Cheat Sheet»."""

    BRIEF_TAB: Final[str] = "БРИФ & ОБУЧЕНИЕ"
    CHEAT_TAB: Final[str] = "CHEAT SHEET"

    def __init__(
        self,
        master: Any,
        *,
        on_hint_requested: HintCallback | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("fg_color", DARK_GRAY)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_COLOR)
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="INTEL // KNOWLEDGE BASE",
            text_color=NEON_GREEN,
            font=("Inter", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(9, 2), sticky="ew")

        self.tabs = ctk.CTkTabview(
            self,
            fg_color="#0A0F15",
            segmented_button_fg_color=DARK_BG,
            segmented_button_selected_color="#145A38",
            segmented_button_selected_hover_color="#197545",
            segmented_button_unselected_color=DARK_BG,
            segmented_button_unselected_hover_color=BORDER_COLOR,
            text_color=TEXT_PRIMARY,
            border_width=0,
            corner_radius=6,
        )
        self.tabs.grid(row=1, column=0, padx=8, pady=(2, 8), sticky="nsew")
        brief_tab = self.tabs.add(self.BRIEF_TAB)
        cheat_tab = self.tabs.add(self.CHEAT_TAB)
        brief_tab.grid_columnconfigure(0, weight=1)
        brief_tab.grid_rowconfigure(0, weight=1)
        cheat_tab.grid_columnconfigure(0, weight=1)
        cheat_tab.grid_rowconfigure(0, weight=1)

        self.brief = MissionBriefPanel(
            brief_tab,
            on_hint_requested=on_hint_requested,
        )
        self.brief.grid(row=0, column=0, sticky="nsew")

        self.cheat_sheet = CheatSheetPanel(cheat_tab)
        self.cheat_sheet.grid(row=0, column=0, sticky="nsew")

    def set_mission(self, mission: Mission) -> None:
        self.brief.set_mission(mission)
        self.tabs.set(self.BRIEF_TAB)

    def show_hint(self) -> None:
        self.tabs.set(self.BRIEF_TAB)
        if not self.brief.hint_visible:
            self.brief.toggle_hint()

    def show_cheat_sheet(self, search: str | None = None) -> None:
        self.tabs.set(self.CHEAT_TAB)
        if search is not None:
            self.cheat_sheet.set_search(search)

    def configure_hint_access(self, *, enabled: bool, cost: int = 0) -> None:
        self.brief.configure_hint_access(enabled=enabled, cost=cost)

    @property
    def hint_visible(self) -> bool:
        return self.brief.hint_visible


MissionInfoPanel = MissionPanel


__all__ = [
    "CheatSheetPanel",
    "CyberdeckSidebar",
    "HintCallback",
    "MissionBriefPanel",
    "MissionInfoPanel",
    "MissionListPanel",
    "MissionPanel",
    "MissionSelectionCallback",
    "PlayerProfilePanel",
    "TraceExpiredCallback",
    "TraceMeter",
]
