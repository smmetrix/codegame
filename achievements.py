"""Система достижений GreyHat: Python Cyberdeck."""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Final

from config import (
    ACCENT_CYAN,
    BORDER_COLOR,
    DARK_BG,
    DARK_GRAY,
    FONT_BODY,
    FONT_HEADING,
    FONT_MONO_FAMILY,
    NEON_GREEN,
    TEXT_MUTED,
    TEXT_PRIMARY,
)
from game_state import GameState, KarmaPath, MissionStatus
from sandbox import SandboxResult


FIRST_BLOOD_ID: Final[str] = "first_blood"
LOOP_ADEPT_ID: Final[str] = "loop_adept"
GREY_CARDINAL_ID: Final[str] = "grey_cardinal"
PENTAGON_HACK_ID: Final[str] = "pentagon_hack"
CLEAN_CODE_ID: Final[str] = "clean_code"


@dataclass(frozen=True, slots=True)
class Achievement:
    id: str
    title: str
    description: str
    reward_exp: int
    reward_btc: int
    icon: str


@dataclass(frozen=True, slots=True)
class AchievementUnlock:
    achievement: Achievement
    unlocked_at: str


ACHIEVEMENTS: Final[tuple[Achievement, ...]] = (
    Achievement(
        id=FIRST_BLOOD_ID,
        title="Первая кровь",
        description="Завершить первую сюжетную миссию и получить первый подтвержденный доступ.",
        reward_exp=100,
        reward_btc=25,
        icon="01",
    ),
    Achievement(
        id=LOOP_ADEPT_ID,
        title="Адепт циклов",
        description="Пройти все миссии Tier 2 со списками, for, while и сканированием подсети.",
        reward_exp=300,
        reward_btc=80,
        icon="∞",
    ),
    Achievement(
        id=GREY_CARDINAL_ID,
        title="Серый кардинал",
        description="Завершить не менее восьми миссий и сохранить нейтральный Серый путь кармы.",
        reward_exp=500,
        reward_btc=150,
        icon="GH",
    ),
    Achievement(
        id=PENTAGON_HACK_ID,
        title="Взлом Пентагона",
        description="Завершить элитный аудит банковского файрвола в миссии Tier 5.",
        reward_exp=900,
        reward_btc=300,
        icon="P5",
    ),
    Achievement(
        id=CLEAN_CODE_ID,
        title="Чистый код",
        description="Решить пять разных миссий читаемым Python-кодом без stderr, табов и длинных строк.",
        reward_exp=700,
        reward_btc=220,
        icon="</>",
    ),
)

ACHIEVEMENT_BY_ID: Final[Mapping[str, Achievement]] = MappingProxyType(
    {achievement.id: achievement for achievement in ACHIEVEMENTS}
)

UnlockCallback = Callable[[AchievementUnlock], None]


class AchievementManager:
    """Проверяет условия, выдает награды один раз и сериализует прогресс."""

    SAVE_VERSION: Final[int] = 1

    def __init__(
        self,
        *,
        unlocked_at: Mapping[str, str] | None = None,
        clean_missions: set[str] | None = None,
        completed_minigames: set[str] | None = None,
        on_unlock: UnlockCallback | None = None,
    ) -> None:
        self._unlocked_at: dict[str, str] = {}
        if unlocked_at is not None:
            for achievement_id, timestamp in unlocked_at.items():
                if achievement_id in ACHIEVEMENT_BY_ID and isinstance(timestamp, str):
                    self._unlocked_at[achievement_id] = timestamp
        self.clean_missions = set(clean_missions or ())
        self.completed_minigames = set(completed_minigames or ())
        self._on_unlock = on_unlock

    @property
    def unlocked_ids(self) -> frozenset[str]:
        return frozenset(self._unlocked_at)

    @property
    def unlocked_count(self) -> int:
        return len(self._unlocked_at)

    def is_unlocked(self, achievement_id: str) -> bool:
        if achievement_id not in ACHIEVEMENT_BY_ID:
            raise KeyError(f"Неизвестное достижение: {achievement_id}")
        return achievement_id in self._unlocked_at

    def record_mission_completion(
        self,
        mission_id: str,
        game_state: GameState,
        *,
        source_code: str,
        sandbox_result: SandboxResult,
    ) -> tuple[AchievementUnlock, ...]:
        if self.is_clean_solution(source_code, sandbox_result):
            self.clean_missions.add(mission_id)
        return self.evaluate(game_state)

    def record_minigame_completion(
        self, game_id: str, game_state: GameState
    ) -> tuple[AchievementUnlock, ...]:
        if game_id:
            self.completed_minigames.add(game_id)
        return self.evaluate(game_state)

    def evaluate(self, game_state: GameState) -> tuple[AchievementUnlock, ...]:
        if not isinstance(game_state, GameState):
            raise TypeError("game_state должен быть экземпляром GameState")
        completed = {
            mission_id
            for mission_id, status in game_state.missions.items()
            if status is MissionStatus.COMPLETED
        }
        candidates: list[str] = []
        if completed:
            candidates.append(FIRST_BLOOD_ID)
        if {
            "m04_block_list",
            "m05_password_bruteforce",
            "m06_subnet_scanner",
        } <= completed:
            candidates.append(LOOP_ADEPT_ID)
        if len(completed) >= 8 and game_state.karma_path is KarmaPath.GREY:
            candidates.append(GREY_CARDINAL_ID)
        if "m14_bank_firewall" in completed:
            candidates.append(PENTAGON_HACK_ID)
        if len(self.clean_missions) >= 5:
            candidates.append(CLEAN_CODE_ID)

        unlocked: list[AchievementUnlock] = []
        for achievement_id in candidates:
            if achievement_id in self._unlocked_at:
                continue
            unlocked.append(self._unlock(achievement_id, game_state))
        return tuple(unlocked)

    def _unlock(self, achievement_id: str, game_state: GameState) -> AchievementUnlock:
        achievement = ACHIEVEMENT_BY_ID[achievement_id]
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._unlocked_at[achievement_id] = timestamp
        game_state.add_exp(achievement.reward_exp)
        game_state.add_bitcoins(achievement.reward_btc)
        unlock = AchievementUnlock(achievement=achievement, unlocked_at=timestamp)
        if self._on_unlock is not None:
            self._on_unlock(unlock)
        return unlock

    @staticmethod
    def is_clean_solution(source_code: str, result: SandboxResult) -> bool:
        """Простая прозрачная проверка качества без изменения кода игрока."""

        if not isinstance(source_code, str) or not source_code.strip():
            return False
        if not isinstance(result, SandboxResult) or not result.success or result.stderr:
            return False
        lines = source_code.splitlines()
        if any(
            "\t" in line or line.rstrip() != line or len(line) > 100 or ";" in line
            for line in lines
        ):
            return False
        try:
            tree = ast.parse(source_code, mode="exec")
        except SyntaxError:
            return False
        forbidden = (ast.Global, ast.Nonlocal)
        return not any(isinstance(node, forbidden) for node in ast.walk(tree))

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.SAVE_VERSION,
            "unlocked_at": dict(sorted(self._unlocked_at.items())),
            "clean_missions": sorted(self.clean_missions),
            "completed_minigames": sorted(self.completed_minigames),
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any] | None,
        *,
        on_unlock: UnlockCallback | None = None,
    ) -> AchievementManager:
        if data is None:
            return cls(on_unlock=on_unlock)
        if not isinstance(data, Mapping):
            raise TypeError("Данные достижений должны быть Mapping")
        version = data.get("version", cls.SAVE_VERSION)
        if version != cls.SAVE_VERSION:
            raise ValueError(f"Неподдерживаемая версия достижений: {version}")
        unlocked = data.get("unlocked_at", {})
        clean = data.get("clean_missions", [])
        minigames = data.get("completed_minigames", [])
        if not isinstance(unlocked, Mapping):
            raise TypeError("unlocked_at должен быть Mapping")
        if not isinstance(clean, (list, tuple, set)):
            raise TypeError("clean_missions должен быть списком")
        if not isinstance(minigames, (list, tuple, set)):
            raise TypeError("completed_minigames должен быть списком")
        return cls(
            unlocked_at={str(key): str(value) for key, value in unlocked.items()},
            clean_missions={str(item) for item in clean},
            completed_minigames={str(item) for item in minigames},
            on_unlock=on_unlock,
        )

    def set_unlock_callback(self, callback: UnlockCallback | None) -> None:
        self._on_unlock = callback


class AchievementsWindow:
    """CustomTkinter-окно со статусом всех достижений."""

    def __init__(
        self,
        master: Any,
        manager: AchievementManager,
    ) -> None:
        import customtkinter as ctk

        self.ctk = ctk
        self.manager = manager
        self.window = ctk.CTkToplevel(master)
        self.window.title("GreyHat // Achievements")
        self.window.geometry("680x610")
        self.window.minsize(540, 450)
        self.window.configure(fg_color=DARK_BG)
        self.window.transient(master)
        self.window.grab_set()
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.window,
            text="ACHIEVEMENT VAULT",
            text_color=NEON_GREEN,
            font=("Inter", 22, "bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=22, pady=(18, 3), sticky="ew")
        ctk.CTkLabel(
            self.window,
            text=f"UNLOCKED {manager.unlocked_count} / {len(ACHIEVEMENTS)}",
            text_color=ACCENT_CYAN,
            font=(FONT_MONO_FAMILY, 11, "bold"),
            anchor="w",
        ).grid(row=1, column=0, padx=22, pady=(0, 10), sticky="ew")

        scroll = ctk.CTkScrollableFrame(
            self.window,
            fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=ACCENT_CYAN,
        )
        scroll.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        for row, achievement in enumerate(ACHIEVEMENTS):
            self._create_card(scroll, row, achievement)

    def _create_card(self, parent: Any, row: int, achievement: Achievement) -> None:
        ctk = self.ctk
        unlocked = self.manager.is_unlocked(achievement.id)
        card = ctk.CTkFrame(
            parent,
            fg_color="#102219" if unlocked else DARK_GRAY,
            corner_radius=8,
            border_width=1,
            border_color=NEON_GREEN if unlocked else BORDER_COLOR,
        )
        card.grid(row=row, column=0, padx=5, pady=6, sticky="ew")
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            card,
            text=achievement.icon if unlocked else "?",
            width=52,
            height=52,
            corner_radius=6,
            fg_color="#0A2D1B" if unlocked else DARK_BG,
            text_color=NEON_GREEN if unlocked else TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 14, "bold"),
        ).grid(row=0, column=0, rowspan=3, padx=12, pady=12)
        ctk.CTkLabel(
            card,
            text=achievement.title if unlocked else "ЗАШИФРОВАНО",
            text_color=TEXT_PRIMARY if unlocked else TEXT_MUTED,
            font=FONT_HEADING,
            anchor="w",
        ).grid(row=0, column=1, padx=3, pady=(10, 1), sticky="ew")
        ctk.CTkLabel(
            card,
            text=achievement.description,
            text_color=TEXT_MUTED,
            font=FONT_BODY,
            wraplength=470,
            justify="left",
            anchor="w",
        ).grid(row=1, column=1, padx=3, pady=2, sticky="ew")
        ctk.CTkLabel(
            card,
            text=f"+{achievement.reward_exp} EXP  +{achievement.reward_btc} BTC",
            text_color=NEON_GREEN if unlocked else ACCENT_CYAN,
            font=(FONT_MONO_FAMILY, 10),
            anchor="w",
        ).grid(row=2, column=1, padx=3, pady=(1, 10), sticky="ew")


__all__ = [
    "ACHIEVEMENTS",
    "ACHIEVEMENT_BY_ID",
    "CLEAN_CODE_ID",
    "FIRST_BLOOD_ID",
    "GREY_CARDINAL_ID",
    "LOOP_ADEPT_ID",
    "PENTAGON_HACK_ID",
    "Achievement",
    "AchievementManager",
    "AchievementUnlock",
    "AchievementsWindow",
    "UnlockCallback",
]
