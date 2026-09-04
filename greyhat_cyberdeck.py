"""GreyHat: Python Cyberdeck — standalone offline desktop game.

This single file contains the cyberpunk UI, campaign, persistent game state,
and isolated educational Python sandbox. Run it with Python 3.11+ after
installing CustomTkinter.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import hashlib
import io
import ipaddress
import json
import math
import multiprocessing
import os
import re
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from multiprocessing.connection import Connection
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Final, Mapping


# ==================== Embedded config.py ====================


APP_NAME: Final[str] = "GreyHat: Python Cyberdeck"
APP_VERSION: Final[str] = "0.1.0"
SAVE_FILE_NAME: Final[str] = "greyhat_save.json"

BASE_DIR: Final[Path] = Path(__file__).resolve().parent
ASSETS_DIR: Final[Path] = BASE_DIR / "assets"
SOUNDS_DIR: Final[Path] = ASSETS_DIR / "sounds"

# Cyberpunk Dark palette
NEON_GREEN: Final[str] = "#00FF66"
DARK_BG: Final[str] = "#0D1117"
ACCENT_CYAN: Final[str] = "#00E5FF"
WARNING_RED: Final[str] = "#FF3366"
DARK_GRAY: Final[str] = "#161B22"
GRAY: Final[str] = DARK_GRAY

TEXT_PRIMARY: Final[str] = "#E6EDF3"
TEXT_MUTED: Final[str] = "#8B949E"
BORDER_COLOR: Final[str] = "#30363D"
SUCCESS_COLOR: Final[str] = NEON_GREEN
TRANSPARENT: Final[str] = "transparent"

COLORS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "neon_green": NEON_GREEN,
        "dark_bg": DARK_BG,
        "accent_cyan": ACCENT_CYAN,
        "warning_red": WARNING_RED,
        "gray": DARK_GRAY,
        "background": DARK_BG,
        "panel": DARK_GRAY,
        "primary": NEON_GREEN,
        "accent": ACCENT_CYAN,
        "warning": WARNING_RED,
        "text_primary": TEXT_PRIMARY,
        "text_muted": TEXT_MUTED,
        "border": BORDER_COLOR,
        "success": SUCCESS_COLOR,
        "transparent": TRANSPARENT,
    }
)
COLOR_PALETTE: Final[Mapping[str, str]] = COLORS
BG_COLOR: Final[str] = DARK_BG
ACCENT_COLOR: Final[str] = ACCENT_CYAN
PANEL_COLOR: Final[str] = DARK_GRAY

# Window and interface
WINDOW_WIDTH: Final[int] = 1440
WINDOW_HEIGHT: Final[int] = 900
MIN_WINDOW_WIDTH: Final[int] = 1100
MIN_WINDOW_HEIGHT: Final[int] = 700
SIDEBAR_WIDTH: Final[int] = 250
TERMINAL_HEIGHT: Final[int] = 270
UI_SCALE: Final[float] = 1.0
APPEARANCE_MODE: Final[str] = "dark"
COLOR_THEME: Final[str] = "dark-blue"

# Editor and terminal
TAB_SIZE: Final[int] = 4
AUTOSAVE_INTERVAL_MS: Final[int] = 30_000
CURSOR_BLINK_INTERVAL_MS: Final[int] = 530
MAX_TERMINAL_LINES: Final[int] = 2_000
DEFAULT_SANDBOX_TIMEOUT_SECONDS: Final[float] = 3.0
MAX_SANDBOX_OUTPUT_CHARS: Final[int] = 50_000

# Fonts. CustomTkinter принимает кортежи (family, size, style).
FONT_UI_FAMILY: Final[str] = "Inter"
FONT_MONO_FAMILY: Final[str] = "JetBrains Mono"
FONT_FALLBACK_UI: Final[str] = "Arial"
FONT_FALLBACK_MONO: Final[str] = "Courier New"

FONT_TITLE: Final[tuple[str, int, str]] = (FONT_UI_FAMILY, 24, "bold")
FONT_HEADING: Final[tuple[str, int, str]] = (FONT_UI_FAMILY, 18, "bold")
FONT_BODY: Final[tuple[str, int]] = (FONT_UI_FAMILY, 14)
FONT_SMALL: Final[tuple[str, int]] = (FONT_UI_FAMILY, 12)
FONT_CODE: Final[tuple[str, int]] = (FONT_MONO_FAMILY, 14)
FONT_TERMINAL: Final[tuple[str, int]] = (FONT_MONO_FAMILY, 13)
FONTS: Final[Mapping[str, tuple[str, int] | tuple[str, int, str]]] = MappingProxyType(
    {
        "title": FONT_TITLE,
        "heading": FONT_HEADING,
        "body": FONT_BODY,
        "small": FONT_SMALL,
        "code": FONT_CODE,
        "terminal": FONT_TERMINAL,
    }
)


@dataclass(frozen=True, slots=True)
class SoundCue:
    """Настройки одного звукового события интерфейса."""

    file_name: str
    volume: float

    def __post_init__(self) -> None:
        if not self.file_name or Path(self.file_name).name != self.file_name:
            raise ValueError("file_name должен быть непустым именем файла")
        if not 0.0 <= self.volume <= 1.0:
            raise ValueError("Громкость должна находиться в диапазоне от 0 до 1")

    @property
    def path(self) -> Path:
        return SOUNDS_DIR / self.file_name


SOUND_ENABLED: Final[bool] = True
MASTER_VOLUME: Final[float] = 0.65
SOUND_CUES: Final[Mapping[str, SoundCue]] = MappingProxyType(
    {
        "ui_click": SoundCue("ui_click.wav", 0.45),
        "terminal_key": SoundCue("terminal_key.wav", 0.18),
        "command_success": SoundCue("command_success.wav", 0.70),
        "command_error": SoundCue("command_error.wav", 0.70),
        "mission_complete": SoundCue("mission_complete.wav", 0.85),
        "notification": SoundCue("notification.wav", 0.55),
        "darknet_purchase": SoundCue("darknet_purchase.wav", 0.75),
    }
)
SOUND_FILES: Final[Mapping[str, Path]] = MappingProxyType(
    {event: cue.path for event, cue in SOUND_CUES.items()}
)


def sound_path(event: str, *, require_existing: bool = False) -> Path:
    """Возвращает путь к звуку события.

    ``require_existing=True`` удобно для аудиодвижка: вместо поздней ошибки
    декодера будет сразу выброшен понятный ``FileNotFoundError``.
    """

    try:
        path = SOUND_CUES[event].path
    except KeyError as exc:
        raise KeyError(f"Неизвестное звуковое событие: {event}") from exc
    if require_existing and not path.is_file():
        raise FileNotFoundError(f"Звуковой файл не найден: {path}")
    return path


__all__ = [
    "ACCENT_COLOR",
    "ACCENT_CYAN",
    "APP_NAME",
    "APP_VERSION",
    "APPEARANCE_MODE",
    "ASSETS_DIR",
    "AUTOSAVE_INTERVAL_MS",
    "BASE_DIR",
    "BG_COLOR",
    "BORDER_COLOR",
    "COLORS",
    "COLOR_PALETTE",
    "COLOR_THEME",
    "CURSOR_BLINK_INTERVAL_MS",
    "DARK_BG",
    "DARK_GRAY",
    "DEFAULT_SANDBOX_TIMEOUT_SECONDS",
    "FONT_BODY",
    "FONT_CODE",
    "FONT_HEADING",
    "FONTS",
    "FONT_MONO_FAMILY",
    "FONT_SMALL",
    "FONT_TERMINAL",
    "FONT_TITLE",
    "FONT_UI_FAMILY",
    "GRAY",
    "MASTER_VOLUME",
    "MAX_SANDBOX_OUTPUT_CHARS",
    "MAX_TERMINAL_LINES",
    "MIN_WINDOW_HEIGHT",
    "MIN_WINDOW_WIDTH",
    "NEON_GREEN",
    "PANEL_COLOR",
    "SAVE_FILE_NAME",
    "SIDEBAR_WIDTH",
    "SOUND_CUES",
    "SOUND_ENABLED",
    "SOUND_FILES",
    "SOUNDS_DIR",
    "SoundCue",
    "TAB_SIZE",
    "TERMINAL_HEIGHT",
    "TEXT_MUTED",
    "TEXT_PRIMARY",
    "TRANSPARENT",
    "UI_SCALE",
    "WARNING_RED",
    "WINDOW_HEIGHT",
    "WINDOW_WIDTH",
    "sound_path",
]

# ==================== Embedded game_state.py ====================


class GameStateError(Exception):
    """Базовая ошибка управления игровым состоянием."""


class InsufficientFundsError(GameStateError):
    """На балансе недостаточно BTC для операции."""


class InvalidSaveError(GameStateError):
    """Файл сохранения поврежден или имеет неподдерживаемый формат."""


class HackerRank(str, Enum):
    SCRIPT_KIDDIE = "Script Kiddie"
    CODE_BREAKER = "Code Breaker"
    NET_RUNNER = "Net Runner"
    GREY_HAT = "Grey Hat"
    CYBER_PHANTOM = "Cyber Phantom"
    ZERO_DAY = "Zero Day Legend"


class MissionStatus(str, Enum):
    LOCKED = "locked"
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class KarmaPath(str, Enum):
    WHITE = "Белый"
    GREY = "Серый"
    BLACK = "Черный"


_RANK_THRESHOLDS: tuple[tuple[int, HackerRank], ...] = (
    (0, HackerRank.SCRIPT_KIDDIE),
    (250, HackerRank.CODE_BREAKER),
    (750, HackerRank.NET_RUNNER),
    (1_750, HackerRank.GREY_HAT),
    (4_000, HackerRank.CYBER_PHANTOM),
    (8_000, HackerRank.ZERO_DAY),
)


def _require_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} должен быть целым числом")
    if value < 0:
        raise ValueError(f"{field_name} не может быть отрицательным")
    return value


def _require_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} должен быть строкой")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} не может быть пустым")
    if len(normalized) > 128:
        raise ValueError(f"{field_name} не может быть длиннее 128 символов")
    return normalized


@dataclass(slots=True)
class GameState:
    """Полное изменяемое состояние прохождения.

    Карма хранится числом от -100 до 100. Значения до -25 относятся к
    черному пути, от 25 — к белому, промежуточные — к серому.
    """

    bitcoins: int = 0
    exp: int = 0
    missions: dict[str, MissionStatus] = field(default_factory=dict)
    purchased_upgrades: set[str] = field(default_factory=set)
    inventory: dict[str, int] = field(default_factory=dict)
    karma: int = 0

    SAVE_VERSION: ClassVar[int] = 1
    MIN_KARMA: ClassVar[int] = -100
    MAX_KARMA: ClassVar[int] = 100

    def __post_init__(self) -> None:
        self.bitcoins = _require_non_negative_int(self.bitcoins, "bitcoins")
        self.exp = _require_non_negative_int(self.exp, "exp")
        if isinstance(self.karma, bool) or not isinstance(self.karma, int):
            raise TypeError("karma должна быть целым числом")
        self.karma = max(self.MIN_KARMA, min(self.MAX_KARMA, self.karma))

        self.missions = {
            _require_identifier(mission_id, "mission_id"): self._coerce_status(status)
            for mission_id, status in self.missions.items()
        }
        self.purchased_upgrades = {
            _require_identifier(upgrade_id, "upgrade_id")
            for upgrade_id in self.purchased_upgrades
        }
        normalized_inventory: dict[str, int] = {}
        for item_id, quantity in self.inventory.items():
            normalized_id = _require_identifier(item_id, "item_id")
            normalized_quantity = _require_non_negative_int(quantity, "quantity")
            if normalized_quantity > 0:
                normalized_inventory[normalized_id] = normalized_quantity
        self.inventory = normalized_inventory

    @staticmethod
    def _coerce_status(status: MissionStatus | str) -> MissionStatus:
        if isinstance(status, MissionStatus):
            return status
        try:
            return MissionStatus(status)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Неизвестный статус миссии: {status!r}") from exc

    @property
    def rank(self) -> HackerRank:
        current = HackerRank.SCRIPT_KIDDIE
        for required_exp, rank in _RANK_THRESHOLDS:
            if self.exp < required_exp:
                break
            current = rank
        return current

    @property
    def hacker_rank(self) -> HackerRank:
        return self.rank

    @property
    def karma_path(self) -> KarmaPath:
        if self.karma >= 25:
            return KarmaPath.WHITE
        if self.karma <= -25:
            return KarmaPath.BLACK
        return KarmaPath.GREY

    @property
    def balance(self) -> int:
        """Совместимый псевдоним баланса BTC."""

        return self.bitcoins

    @balance.setter
    def balance(self, value: int) -> None:
        self.bitcoins = _require_non_negative_int(value, "balance")

    @property
    def mission_statuses(self) -> dict[str, MissionStatus]:
        return self.missions

    @property
    def bought_upgrades(self) -> set[str]:
        return self.purchased_upgrades

    def add_bitcoins(self, amount: int) -> int:
        amount = _require_non_negative_int(amount, "amount")
        self.bitcoins += amount
        return self.bitcoins

    def spend_bitcoins(self, amount: int) -> int:
        amount = _require_non_negative_int(amount, "amount")
        if amount > self.bitcoins:
            raise InsufficientFundsError(
                f"Недостаточно BTC: требуется {amount}, доступно {self.bitcoins}"
            )
        self.bitcoins -= amount
        return self.bitcoins

    def add_exp(self, amount: int) -> HackerRank:
        self.exp += _require_non_negative_int(amount, "amount")
        return self.rank

    def adjust_karma(self, delta: int) -> KarmaPath:
        if isinstance(delta, bool) or not isinstance(delta, int):
            raise TypeError("delta должна быть целым числом")
        self.karma = max(self.MIN_KARMA, min(self.MAX_KARMA, self.karma + delta))
        return self.karma_path

    def set_mission_status(
        self, mission_id: str, status: MissionStatus | str
    ) -> MissionStatus:
        mission_id = _require_identifier(mission_id, "mission_id")
        normalized_status = self._coerce_status(status)
        self.missions[mission_id] = normalized_status
        return normalized_status

    def get_mission_status(self, mission_id: str) -> MissionStatus:
        mission_id = _require_identifier(mission_id, "mission_id")
        return self.missions.get(mission_id, MissionStatus.LOCKED)

    def complete_mission(
        self,
        mission_id: str,
        *,
        bitcoins_reward: int = 0,
        exp_reward: int = 0,
        karma_delta: int = 0,
    ) -> bool:
        """Завершает миссию и ровно один раз начисляет награду."""

        mission_id = _require_identifier(mission_id, "mission_id")
        bitcoins_reward = _require_non_negative_int(bitcoins_reward, "bitcoins_reward")
        exp_reward = _require_non_negative_int(exp_reward, "exp_reward")
        if isinstance(karma_delta, bool) or not isinstance(karma_delta, int):
            raise TypeError("karma_delta должна быть целым числом")
        if self.get_mission_status(mission_id) is MissionStatus.COMPLETED:
            return False
        self.missions[mission_id] = MissionStatus.COMPLETED
        self.add_bitcoins(bitcoins_reward)
        self.add_exp(exp_reward)
        self.adjust_karma(karma_delta)
        return True

    def purchase_upgrade(self, upgrade_id: str, price: int) -> bool:
        """Покупает улучшение; повторная покупка ничего не списывает."""

        upgrade_id = _require_identifier(upgrade_id, "upgrade_id")
        price = _require_non_negative_int(price, "price")
        if upgrade_id in self.purchased_upgrades:
            return False
        self.spend_bitcoins(price)
        self.purchased_upgrades.add(upgrade_id)
        return True

    def add_item(self, item_id: str, quantity: int = 1) -> int:
        item_id = _require_identifier(item_id, "item_id")
        quantity = _require_non_negative_int(quantity, "quantity")
        if quantity == 0:
            return self.inventory.get(item_id, 0)
        self.inventory[item_id] = self.inventory.get(item_id, 0) + quantity
        return self.inventory[item_id]

    def remove_item(self, item_id: str, quantity: int = 1) -> int:
        item_id = _require_identifier(item_id, "item_id")
        quantity = _require_non_negative_int(quantity, "quantity")
        available = self.inventory.get(item_id, 0)
        if quantity > available:
            raise GameStateError(
                f"Недостаточно предметов {item_id!r}: требуется {quantity}, доступно {available}"
            )
        remaining = available - quantity
        if remaining:
            self.inventory[item_id] = remaining
        else:
            self.inventory.pop(item_id, None)
        return remaining

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.SAVE_VERSION,
            "bitcoins": self.bitcoins,
            "exp": self.exp,
            "rank": self.rank.value,
            "missions": {
                mission_id: status.value
                for mission_id, status in sorted(self.missions.items())
            },
            "purchased_upgrades": sorted(self.purchased_upgrades),
            "inventory": dict(sorted(self.inventory.items())),
            "karma": self.karma,
            "karma_path": self.karma_path.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GameState:
        if not isinstance(data, Mapping):
            raise InvalidSaveError("Корень сохранения должен быть JSON-объектом")
        version = data.get("version", cls.SAVE_VERSION)
        if version != cls.SAVE_VERSION:
            raise InvalidSaveError(
                f"Версия сохранения {version!r} не поддерживается; ожидается {cls.SAVE_VERSION}"
            )

        missions = data.get("missions", {})
        upgrades = data.get("purchased_upgrades", [])
        inventory = data.get("inventory", {})
        if not isinstance(missions, Mapping):
            raise InvalidSaveError("Поле missions должно быть объектом")
        if not isinstance(upgrades, (list, tuple, set)):
            raise InvalidSaveError("Поле purchased_upgrades должно быть списком")
        if not isinstance(inventory, Mapping):
            raise InvalidSaveError("Поле inventory должно быть объектом")

        try:
            return cls(
                bitcoins=data.get("bitcoins", 0),
                exp=data.get("exp", 0),
                missions=dict(missions),
                purchased_upgrades=set(upgrades),
                inventory=dict(inventory),
                karma=data.get("karma", 0),
            )
        except (TypeError, ValueError) as exc:
            raise InvalidSaveError(f"Некорректные данные сохранения: {exc}") from exc

    def save(self, path: str | Path) -> Path:
        """Атомарно записывает состояние в UTF-8 JSON."""

        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temp_name = temporary.name
                json.dump(self.to_dict(), temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temp_name, destination)
        except OSError as exc:
            if temp_name is not None:
                try:
                    Path(temp_name).unlink(missing_ok=True)
                except OSError:
                    temp_name = None
            raise GameStateError(
                f"Не удалось сохранить игру в {destination}: {exc}"
            ) from exc
        return destination

    @classmethod
    def load(cls, path: str | Path) -> GameState:
        source = Path(path).expanduser()
        try:
            with source.open("r", encoding="utf-8") as save_file:
                data = json.load(save_file)
        except FileNotFoundError as exc:
            raise InvalidSaveError(f"Файл сохранения не найден: {source}") from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InvalidSaveError(
                f"Не удалось прочитать сохранение {source}: {exc}"
            ) from exc
        return cls.from_dict(data)


__all__ = [
    "GameState",
    "GameStateError",
    "HackerRank",
    "InsufficientFundsError",
    "InvalidSaveError",
    "KarmaPath",
    "MissionStatus",
]

# ==================== Embedded sandbox.py ====================


DEFAULT_TIMEOUT_SECONDS: Final[float] = 3.0
DEFAULT_MAX_OUTPUT_CHARS: Final[int] = 50_000
DEFAULT_MAX_MEMORY_MB: Final[int] = 256
DEFAULT_MAX_AST_NODES: Final[int] = 10_000
MAX_SOURCE_CHARS: Final[int] = 100_000
MAX_SERIALIZED_ITEMS: Final[int] = 500
MAX_VALUE_DEPTH: Final[int] = 8

_ALLOWED_MODULES: Final[frozenset[str]] = frozenset(
    {"json", "math", "re", "statistics", "string"}
)
_BLOCKED_MODULES: Final[frozenset[str]] = frozenset(
    {
        "asyncio",
        "builtins",
        "ctypes",
        "importlib",
        "inspect",
        "io",
        "marshal",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "resource",
        "shutil",
        "signal",
        "socket",
        "subprocess",
        "sys",
        "tempfile",
        "threading",
        "traceback",
        "types",
    }
)
_BLOCKED_NAMES: Final[frozenset[str]] = frozenset(
    {
        "__builtins__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "exit",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "memoryview",
        "open",
        "os",
        "quit",
        "setattr",
        "subprocess",
        "sys",
        "vars",
    }
)
_UNSET: Final[object] = object()
_HOST_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*"
    r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
)


class SandboxError(Exception):
    """Базовая ошибка песочницы."""


class SandboxSecurityError(SandboxError):
    """Код содержит запрещенную конструкцию."""


class SandboxOutputLimitError(SandboxError):
    """Программа превысила допустимый объем консольного вывода."""


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """Итог одного запуска пользовательской программы."""

    success: bool
    output: str = ""
    variables: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    stderr: str = ""
    timed_out: bool = False
    duration: float = 0.0
    validation_errors: tuple[str, ...] = ()

    @property
    def stdout(self) -> str:
        return self.output

    @property
    def console_output(self) -> str:
        if not self.stderr:
            return self.output
        separator = "" if not self.output or self.output.endswith("\n") else "\n"
        return f"{self.output}{separator}{self.stderr}"

    @property
    def return_value(self) -> Any:
        return self.result

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "stdout": self.output,
            "stderr": self.stderr,
            "console_output": self.console_output,
            "variables": dict(self.variables),
            "result": self.result,
            "error": self.error,
            "timed_out": self.timed_out,
            "duration": self.duration,
            "validation_errors": list(self.validation_errors),
        }


class _LimitedTextBuffer(io.StringIO):
    def __init__(self, limit: int) -> None:
        super().__init__()
        self._limit = limit
        self._written = 0
        self.exceeded = False

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("В консоль можно записывать только строки")
        available = self._limit - self._written
        if available > 0:
            super().write(text[:available])
            self._written += min(len(text), available)
        if len(text) > available:
            self.exceeded = True
        return len(text)


class _SecurityVisitor(ast.NodeVisitor):
    """Отклоняет способы добраться до окружения интерпретатора."""

    def __init__(self, max_nodes: int) -> None:
        self.max_nodes = max_nodes
        self.node_count = 0

    def generic_visit(self, node: ast.AST) -> None:
        self.node_count += 1
        if self.node_count > self.max_nodes:
            raise SandboxSecurityError(
                f"Программа слишком сложная: максимум {self.max_nodes} AST-узлов"
            )
        super().generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            raise SandboxSecurityError(
                f"Относительный импорт запрещен (строка {node.lineno})"
            )
        if node.module is None:
            raise SandboxSecurityError(f"Некорректный импорт (строка {node.lineno})")
        self._check_module(node.module, node.lineno)
        for alias in node.names:
            if alias.name == "*" or alias.name.startswith("_"):
                raise SandboxSecurityError(
                    f"Импорт {alias.name!r} запрещен (строка {node.lineno})"
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise SandboxSecurityError(
                f"Доступ к служебному атрибуту {node.attr!r} запрещен "
                f"(строка {node.lineno})"
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in _BLOCKED_NAMES or node.id.startswith("__"):
            raise SandboxSecurityError(
                f"Имя {node.id!r} запрещено (строка {node.lineno})"
            )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        value = node.value
        if type(value) in (str, bytes) and len(value) > DEFAULT_MAX_OUTPUT_CHARS:
            raise SandboxSecurityError(
                f"Слишком большой литерал (строка {getattr(node, 'lineno', '?')})"
            )
        self.generic_visit(node)

    def visit_MatchClass(self, node: ast.MatchClass) -> None:
        # Class patterns resolve keyword attributes internally, so they must
        # follow the same private-attribute rule as ordinary attribute access.
        for attribute in node.kwd_attrs:
            if attribute.startswith("_"):
                raise SandboxSecurityError(
                    f"Сопоставление по служебному атрибуту {attribute!r} запрещено "
                    f"(строка {node.lineno})"
                )
        self.generic_visit(node)

    @staticmethod
    def _check_module(module_name: str, line: int) -> None:
        root = module_name.split(".", maxsplit=1)[0]
        if (
            root in _BLOCKED_MODULES
            or root not in _ALLOWED_MODULES
            or module_name != root
        ):
            allowed = ", ".join(sorted(_ALLOWED_MODULES))
            raise SandboxSecurityError(
                f"Модуль {module_name!r} запрещен (строка {line}). "
                f"Доступны только: {allowed}"
            )


def _parse_and_validate(source: str, max_nodes: int) -> ast.Module:
    try:
        tree = ast.parse(source, filename="<user_code>", mode="exec")
    except SyntaxError as exc:
        location = f"строка {exc.lineno}"
        if exc.offset is not None:
            location += f", позиция {exc.offset}"
        raise SandboxError(f"SyntaxError: {exc.msg} ({location})") from exc
    _SecurityVisitor(max_nodes).visit(tree)
    return tree


def _validate_host(host: str) -> str:
    if type(host) is not str:
        raise TypeError("host должен быть строкой")
    normalized = host.strip().lower()
    if not normalized:
        raise ValueError("host не может быть пустым")
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        if _HOST_PATTERN.fullmatch(normalized) is None:
            raise ValueError(f"Некорректный host: {host!r}") from None
    return normalized


def ping(host: str) -> bool:
    """Детерминированно симулирует доступность узла без реальной сети."""

    normalized = _validate_host(host)
    if normalized in {"0.0.0.0", "255.255.255.255", "offline", "offline.local"}:
        return False
    if normalized in {"127.0.0.1", "::1", "localhost", "cyberdeck.local"}:
        return True
    score = hashlib.sha256(f"ping:{normalized}".encode("utf-8")).digest()[0]
    return score < 210


def scan_ports(ip: str) -> list[int]:
    """Возвращает стабильный набор виртуальных открытых TCP-портов."""

    normalized = _validate_host(ip)
    known_hosts: Mapping[str, tuple[int, ...]] = MappingProxyType(
        {
            "127.0.0.1": (22, 80, 443, 8080),
            "::1": (22, 80, 443, 8080),
            "localhost": (22, 80, 443, 8080),
            "cyberdeck.local": (22, 80, 443, 31337),
            "vault.greyhat": (21, 22, 443, 3306),
        }
    )
    if normalized in known_hosts:
        return list(known_hosts[normalized])

    candidates = (21, 22, 25, 53, 80, 110, 143, 443, 3306, 5432, 8080, 8443)
    digest = hashlib.sha256(f"ports:{normalized}".encode("utf-8")).digest()
    ports = [port for index, port in enumerate(candidates) if digest[index] % 3 == 0]
    if not ports:
        ports.append(candidates[digest[0] % len(candidates)])
    return sorted(ports[:6])


def send_payload(target: str, data: str | bytes) -> dict[str, Any]:
    """Симулирует отправку payload и возвращает проверяемую квитанцию."""

    normalized = _validate_host(target)
    if type(data) not in (str, bytes):
        raise TypeError("data должен быть строкой или bytes")
    payload = data.encode("utf-8") if type(data) is str else data
    if not payload:
        raise ValueError("Нельзя отправить пустой payload")
    if len(payload) > 8_192:
        raise ValueError("Payload не может превышать 8192 байта")
    digest = hashlib.sha256(normalized.encode("utf-8") + b":" + payload).hexdigest()
    return {
        "accepted": ping(normalized),
        "target": normalized,
        "bytes_sent": len(payload),
        "receipt": digest[:16],
    }


def decrypt_caesar(text: str, shift: int) -> str:
    """Расшифровывает Caesar cipher для латиницы и русского алфавита."""

    if type(text) is not str:
        raise TypeError("text должен быть строкой")
    if isinstance(shift, bool) or not isinstance(shift, int):
        raise TypeError("shift должен быть целым числом")

    alphabets = (
        "abcdefghijklmnopqrstuvwxyz",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ",
    )
    lookup = {character: alphabet for alphabet in alphabets for character in alphabet}
    decrypted: list[str] = []
    for character in text:
        alphabet = lookup.get(character)
        if alphabet is None:
            decrypted.append(character)
            continue
        position = alphabet.index(character)
        decrypted.append(alphabet[(position - shift) % len(alphabet)])
    return "".join(decrypted)


class _SafeModule:
    """Read-only facade that does not expose a module's imported dependencies."""

    __slots__ = ("_module_name", "_values")

    def __init__(self, module_name: str, values: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_module_name", module_name)
        object.__setattr__(self, "_values", MappingProxyType(dict(values)))

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        values: Mapping[str, Any] = object.__getattribute__(self, "_values")
        try:
            return values[name]
        except KeyError as exc:
            module_name = object.__getattribute__(self, "_module_name")
            raise AttributeError(
                f"Безопасный модуль {module_name!r} не предоставляет {name!r}"
            ) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        del value
        raise AttributeError(f"Безопасный модуль доступен только для чтения: {name}")

    def __repr__(self) -> str:
        module_name = object.__getattribute__(self, "_module_name")
        return f"<safe module {module_name!r}>"


_SAFE_MODULES: dict[str, _SafeModule] | None = None


def _build_safe_modules() -> dict[str, _SafeModule]:
    """Creates curated facades; raw modules are never returned to user code."""

    import json
    import math as math_module
    import re as re_module
    import statistics
    import string

    selected_names: Mapping[str, tuple[str, ...]] = {
        "json": (
            "JSONDecodeError",
            "JSONDecoder",
            "JSONEncoder",
            "dumps",
            "loads",
        ),
        "re": (
            "A",
            "ASCII",
            "DEBUG",
            "DOTALL",
            "I",
            "IGNORECASE",
            "L",
            "LOCALE",
            "M",
            "MULTILINE",
            "NOFLAG",
            "Pattern",
            "RegexFlag",
            "S",
            "T",
            "TEMPLATE",
            "U",
            "UNICODE",
            "VERBOSE",
            "X",
            "compile",
            "escape",
            "findall",
            "finditer",
            "fullmatch",
            "match",
            "purge",
            "search",
            "split",
            "sub",
            "subn",
        ),
        "statistics": (
            "NormalDist",
            "StatisticsError",
            "correlation",
            "covariance",
            "fmean",
            "geometric_mean",
            "harmonic_mean",
            "linear_regression",
            "mean",
            "median",
            "median_grouped",
            "median_high",
            "median_low",
            "mode",
            "multimode",
            "pstdev",
            "pvariance",
            "quantiles",
            "stdev",
            "variance",
        ),
        "string": (
            "Template",
            "ascii_letters",
            "ascii_lowercase",
            "ascii_uppercase",
            "capwords",
            "digits",
            "hexdigits",
            "octdigits",
            "printable",
            "punctuation",
            "whitespace",
        ),
    }
    real_modules: Mapping[str, Any] = {
        "json": json,
        "re": re_module,
        "statistics": statistics,
        "string": string,
    }
    facades = {
        name: _SafeModule(
            name,
            {
                attribute: getattr(module, attribute)
                for attribute in selected_names[name]
                if hasattr(module, attribute)
            },
        )
        for name, module in real_modules.items()
    }
    facades["math"] = _SafeModule(
        "math",
        {
            attribute: getattr(math_module, attribute)
            for attribute in dir(math_module)
            if not attribute.startswith("_")
        },
    )
    return facades


def _restricted_import(
    name: str,
    globals_dict: Mapping[str, Any] | None = None,
    locals_dict: Mapping[str, Any] | None = None,
    fromlist: tuple[str, ...] | list[str] | None = (),
    level: int = 0,
) -> Any:
    del globals_dict, locals_dict
    if level != 0:
        raise ImportError("Относительные импорты запрещены")
    root = name.split(".", maxsplit=1)[0]
    if root not in _ALLOWED_MODULES or name != root:
        raise ImportError(f"Импорт модуля {name!r} запрещен")
    normalized_fromlist = () if fromlist is None else fromlist
    for imported_name in normalized_fromlist:
        if imported_name == "*" or imported_name.startswith("_"):
            raise ImportError(f"Импорт имени {imported_name!r} запрещен")

    global _SAFE_MODULES
    if _SAFE_MODULES is None:
        _SAFE_MODULES = _build_safe_modules()
    facade = _SAFE_MODULES[name]
    for imported_name in normalized_fromlist:
        if not hasattr(facade, imported_name):
            raise ImportError(
                f"Безопасный модуль {name!r} не предоставляет {imported_name!r}"
            )
    return facade


def _safe_builtins() -> Mapping[str, Any]:
    allowed = {
        "__build_class__": builtins.__build_class__,
        "__import__": _restricted_import,
        "abs": abs,
        "all": all,
        "any": any,
        "ascii": ascii,
        "bin": bin,
        "bool": bool,
        "bytes": bytes,
        "callable": callable,
        "chr": chr,
        "complex": complex,
        "dict": dict,
        "divmod": divmod,
        "enumerate": enumerate,
        "Exception": Exception,
        "filter": filter,
        "float": float,
        "format": format,
        "frozenset": frozenset,
        "hex": hex,
        "IndexError": IndexError,
        "int": int,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "iter": iter,
        "KeyError": KeyError,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "NotImplementedError": NotImplementedError,
        "object": object,
        "oct": oct,
        "ord": ord,
        "OverflowError": OverflowError,
        "pow": pow,
        "print": print,
        "range": range,
        "repr": repr,
        "reversed": reversed,
        "round": round,
        "RuntimeError": RuntimeError,
        "set": set,
        "slice": slice,
        "sorted": sorted,
        "StopIteration": StopIteration,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "TypeError": TypeError,
        "ValueError": ValueError,
        "zip": zip,
    }
    # CPython требует настоящий dict в globals['__builtins__']; MappingProxyType
    # ломает IMPORT_NAME на уровне интерпретатора. Сам словарь недоступен коду:
    # имя __builtins__ и все dunder-атрибуты блокируются AST-проверкой.
    return allowed


def _capture_last_expression(tree: ast.Module) -> ast.Module:
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        expression = tree.body[-1]
        assignment = ast.Assign(
            targets=[ast.Name(id="_sandbox_result", ctx=ast.Store())],
            value=expression.value,
        )
        tree.body[-1] = ast.copy_location(assignment, expression)
        ast.fix_missing_locations(tree)
    return tree


def _safe_value(
    value: Any,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> Any:
    """Копирует только типы, безопасные для unpickle в родительском процессе."""

    value_type = type(value)
    if value is None or value_type in (bool, float):
        return value
    if value_type is int:
        if value.bit_length() > 16_384:
            return "<int: слишком большое значение>"
        return value
    if value_type is str:
        return value[:DEFAULT_MAX_OUTPUT_CHARS]
    if value_type is bytes:
        return value[:DEFAULT_MAX_OUTPUT_CHARS]
    if depth >= MAX_VALUE_DEPTH:
        return "<достигнут предел вложенности>"

    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return "<циклическая ссылка>"

    if value_type in (list, tuple, set, frozenset, dict):
        seen.add(identity)
        try:
            if value_type is dict:
                safe_dict: dict[Any, Any] = {}
                for index, (key, item) in enumerate(value.items()):
                    if index >= MAX_SERIALIZED_ITEMS:
                        break
                    if type(key) not in (str, int, float, bool, bytes, type(None)):
                        continue
                    safe_dict[_safe_value(key, depth=depth + 1, seen=seen)] = (
                        _safe_value(item, depth=depth + 1, seen=seen)
                    )
                return safe_dict

            safe_items = [
                _safe_value(item, depth=depth + 1, seen=seen)
                for index, item in enumerate(value)
                if index < MAX_SERIALIZED_ITEMS
            ]
            if value_type is tuple:
                return tuple(safe_items)
            if value_type is set:
                try:
                    return set(safe_items)
                except TypeError:
                    return safe_items
            if value_type is frozenset:
                try:
                    return frozenset(safe_items)
                except TypeError:
                    return tuple(safe_items)
            return safe_items
        finally:
            seen.remove(identity)

    return f"<{value_type.__name__}: значение недоступно вне песочницы>"


def _format_runtime_error(exc: BaseException) -> str:
    exception_name = type(exc).__name__
    try:
        detail = str(exc)
    except BaseException:
        detail = "не удалось получить описание ошибки"
    detail = detail[:2_000]
    user_line: int | None = None
    extracted = traceback.extract_tb(exc.__traceback__)
    for frame in reversed(extracted):
        if frame.filename == "<user_code>":
            user_line = frame.lineno
            break
    suffix = f" (строка {user_line})" if user_line is not None else ""
    return f"{exception_name}: {detail}{suffix}"


def _apply_resource_limits(timeout: float, max_memory_mb: int) -> None:
    try:
        import resource
    except ImportError:
        return

    memory_bytes = max_memory_mb * 1024 * 1024
    cpu_soft = max(1, math.ceil(timeout))
    limits = (
        (resource.RLIMIT_CORE, (0, 0)),
        (resource.RLIMIT_FSIZE, (0, 0)),
        (resource.RLIMIT_AS, (memory_bytes, memory_bytes)),
        (resource.RLIMIT_CPU, (cpu_soft, cpu_soft + 1)),
    )
    for limit_kind, value in limits:
        try:
            resource.setrlimit(limit_kind, value)
        except (OSError, ValueError):
            continue


def _collect_user_variables(
    globals_dict: Mapping[str, Any], initial_names: frozenset[str]
) -> dict[str, Any]:
    return {
        name: _safe_value(value)
        for name, value in globals_dict.items()
        if name not in initial_names
        and name != "_sandbox_result"
        and not name.startswith("__")
    }


def _worker(
    connection: Connection,
    source: str,
    timeout: float,
    max_output_chars: int,
    max_memory_mb: int,
    max_ast_nodes: int,
    working_directory: str,
) -> None:
    _apply_resource_limits(timeout, max_memory_mb)
    try:
        os.chdir(working_directory)
    except OSError:
        os.chdir(tempfile.gettempdir())

    stdout_buffer = _LimitedTextBuffer(max_output_chars)
    stderr_buffer = _LimitedTextBuffer(max_output_chars)
    globals_dict: dict[str, Any] = {
        "__builtins__": _safe_builtins(),
        "__name__": "__sandbox__",
        "decrypt_caesar": decrypt_caesar,
        "ping": ping,
        "scan_ports": scan_ports,
        "send_payload": send_payload,
    }
    initial_names = frozenset(globals_dict)

    try:
        tree = _capture_last_expression(_parse_and_validate(source, max_ast_nodes))
        compiled = compile(tree, "<user_code>", "exec", dont_inherit=True, optimize=0)
        with (
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            exec(compiled, globals_dict, globals_dict)

        if stdout_buffer.exceeded or stderr_buffer.exceeded:
            raise SandboxOutputLimitError(
                f"Вывод превысил лимит {max_output_chars} символов"
            )

        variables = _collect_user_variables(globals_dict, initial_names)
        payload: dict[str, Any] = {
            "success": True,
            "output": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
            "variables": variables,
            "result": _safe_value(globals_dict.get("_sandbox_result")),
            "error": None,
        }
    except BaseException as exc:
        payload = {
            "success": False,
            "output": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
            "variables": _collect_user_variables(globals_dict, initial_names),
            "result": _safe_value(globals_dict.get("_sandbox_result")),
            "error": _format_runtime_error(exc),
        }

    try:
        connection.send(payload)
    except (BrokenPipeError, EOFError, OSError):
        connection.close()
        return
    connection.close()


def _values_equal(actual: Any, expected: Any) -> bool:
    try:
        return type(actual) is type(expected) and bool(actual == expected)
    except (TypeError, ValueError):
        return False


class Sandbox:
    """Движок безопасного запуска кода для миссий.

    Один экземпляр можно последовательно использовать для любого количества
    запусков: каждый запуск получает новый чистый процесс и namespace.
    """

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
        max_memory_mb: int = DEFAULT_MAX_MEMORY_MB,
        max_ast_nodes: int = DEFAULT_MAX_AST_NODES,
    ) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout должен быть числом")
        if not 0.05 <= float(timeout) <= 30.0:
            raise ValueError("timeout должен быть в диапазоне от 0.05 до 30 секунд")
        for value, name, minimum, maximum in (
            (max_output_chars, "max_output_chars", 100, 1_000_000),
            (max_memory_mb, "max_memory_mb", 64, 2_048),
            (max_ast_nodes, "max_ast_nodes", 100, 100_000),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} должен быть целым числом")
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} должен быть от {minimum} до {maximum}")

        self.timeout = float(timeout)
        self.max_output_chars = max_output_chars
        self.max_memory_mb = max_memory_mb
        self.max_ast_nodes = max_ast_nodes

    def execute(
        self,
        source: str,
        *,
        expected_output: str | None = None,
        expected_variables: Mapping[str, Any] | None = None,
        expected_result: Any = _UNSET,
    ) -> SandboxResult:
        """Запускает код и при необходимости проверяет решение миссии."""

        if not isinstance(source, str):
            raise TypeError("source должен быть строкой")
        if len(source) > MAX_SOURCE_CHARS:
            return SandboxResult(
                success=False,
                error=f"Код превышает лимит {MAX_SOURCE_CHARS} символов",
            )
        if expected_output is not None and not isinstance(expected_output, str):
            raise TypeError("expected_output должен быть строкой или None")
        if expected_variables is not None and not isinstance(
            expected_variables, Mapping
        ):
            raise TypeError("expected_variables должен быть Mapping или None")

        started_at = time.monotonic()
        try:
            _parse_and_validate(source, self.max_ast_nodes)
        except SandboxError as exc:
            return SandboxResult(
                success=False,
                error=str(exc),
                duration=time.monotonic() - started_at,
            )

        # Spawn gives a clean interpreter. Interactive shells have no importable
        # __main__ file, so POSIX falls back to fork instead of failing before
        # the user's code starts. Windows only supports the spawn strategy.
        main_module = sys.modules.get("__main__")
        main_file = getattr(main_module, "__file__", None)
        interactive_main = not main_file or not os.path.isfile(main_file)
        start_method = "fork" if os.name != "nt" and interactive_main else "spawn"
        context = multiprocessing.get_context(start_method)
        receiving, sending = context.Pipe(duplex=False)
        try:
            with tempfile.TemporaryDirectory(prefix="greyhat-sandbox-") as workdir:
                process = context.Process(
                    target=_worker,
                    args=(
                        sending,
                        source,
                        self.timeout,
                        self.max_output_chars,
                        self.max_memory_mb,
                        self.max_ast_nodes,
                        workdir,
                    ),
                    name="GreyHatSandbox",
                    daemon=True,
                )
                try:
                    process.start()
                except (OSError, RuntimeError) as exc:
                    return SandboxResult(
                        success=False,
                        error=f"Не удалось запустить песочницу: {exc}",
                        duration=time.monotonic() - started_at,
                    )
                finally:
                    sending.close()

                if not receiving.poll(self.timeout):
                    self._stop_process(process)
                    return SandboxResult(
                        success=False,
                        error=f"TimeoutError: превышен лимит {self.timeout:g} с",
                        timed_out=True,
                        duration=time.monotonic() - started_at,
                    )

                try:
                    payload = receiving.recv()
                except (EOFError, OSError) as exc:
                    self._stop_process(process)
                    return SandboxResult(
                        success=False,
                        error=f"Процесс песочницы завершился без результата: {exc}",
                        duration=time.monotonic() - started_at,
                    )
                process.join(timeout=0.2)
                if process.is_alive():
                    self._stop_process(process)
                else:
                    process.close()
        finally:
            receiving.close()

        result = SandboxResult(
            success=bool(payload["success"]),
            output=payload["output"],
            stderr=payload["stderr"],
            variables=payload["variables"],
            result=payload["result"],
            error=payload["error"],
            duration=time.monotonic() - started_at,
        )
        if not result.success:
            return result
        return self._validate_result(
            result,
            expected_output=expected_output,
            expected_variables=expected_variables,
            expected_result=expected_result,
        )

    run = execute

    @staticmethod
    def _stop_process(process: multiprocessing.Process) -> None:
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.25)
        if process.is_alive() and hasattr(process, "kill"):
            process.kill()
            process.join(timeout=0.25)
        process.close()

    @staticmethod
    def _validate_result(
        result: SandboxResult,
        *,
        expected_output: str | None,
        expected_variables: Mapping[str, Any] | None,
        expected_result: Any,
    ) -> SandboxResult:
        errors: list[str] = []
        if expected_output is not None and result.output != expected_output:
            errors.append(
                f"Вывод не совпадает: ожидалось {expected_output!r}, "
                f"получено {result.output!r}"
            )
        if expected_variables is not None:
            for name, expected in expected_variables.items():
                if name not in result.variables:
                    errors.append(f"Переменная {name!r} не создана")
                    continue
                actual = result.variables[name]
                if not _values_equal(actual, expected):
                    errors.append(
                        f"Переменная {name!r}: ожидалось {expected!r}, "
                        f"получено {actual!r}"
                    )
        if expected_result is not _UNSET and not _values_equal(
            result.result, expected_result
        ):
            errors.append(
                f"Результат не совпадает: ожидалось {expected_result!r}, "
                f"получено {result.result!r}"
            )
        if not errors:
            return result
        return replace(
            result,
            success=False,
            error="; ".join(errors),
            validation_errors=tuple(errors),
        )


def execute_code(
    source: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    expected_output: str | None = None,
    expected_variables: Mapping[str, Any] | None = None,
    expected_result: Any = _UNSET,
) -> SandboxResult:
    """Функциональный shortcut для единичного запуска."""

    return Sandbox(timeout=timeout).execute(
        source,
        expected_output=expected_output,
        expected_variables=expected_variables,
        expected_result=expected_result,
    )


__all__ = [
    "DEFAULT_MAX_AST_NODES",
    "DEFAULT_MAX_MEMORY_MB",
    "DEFAULT_MAX_OUTPUT_CHARS",
    "DEFAULT_TIMEOUT_SECONDS",
    "Sandbox",
    "SandboxError",
    "SandboxOutputLimitError",
    "SandboxResult",
    "SandboxSecurityError",
    "decrypt_caesar",
    "execute_code",
    "ping",
    "scan_ports",
    "send_payload",
]


# ============================================================================
# Integrated CustomTkinter game client
# ============================================================================


@dataclass(frozen=True, slots=True)
class Mission:
    mission_id: str
    number: int
    title: str
    difficulty: str
    briefing: str
    objective: str
    hint: str
    advanced_hint: str
    starter_code: str
    bitcoins_reward: int
    exp_reward: int
    karma_reward: int = 0
    reward_item: str | None = None


@dataclass(frozen=True, slots=True)
class Upgrade:
    upgrade_id: str
    title: str
    description: str
    price: int


MISSIONS: Final[tuple[Mission, ...]] = (
    Mission(
        mission_id="boot_protocol",
        number=1,
        title="Boot Protocol",
        difficulty="АЗЫ",
        briefing=(
            "Cyberdeck запущен в аварийном режиме. Система допускает только "
            "оператора с позывным ghost. Начнем с переменной и print()."
        ),
        objective=("Запиши строку ghost в переменную handle и выведи: ACCESS: ghost"),
        hint='Строки записываются в кавычках: handle = "ghost".',
        advanced_hint="print() умеет выводить несколько значений через запятую.",
        starter_code=(
            "# Измени позывной и запусти код.\n"
            'handle = "anonymous"\n'
            'print("ACCESS:", handle)\n'
        ),
        bitcoins_reward=20,
        exp_reward=100,
        karma_reward=2,
        reward_item="access_card_l1",
    ),
    Mission(
        mission_id="target_profile",
        number=2,
        title="Target Profile",
        difficulty="АЗЫ",
        briefing=(
            "Для подключения нужны адрес, порт и флаг защищенного канала. "
            "Python хранит эти данные в переменных разных типов."
        ),
        objective=(
            'Создай target = "vault.greyhat", port = 443 и secure = True. '
            "Выведи строку vault.greyhat:443 secure=True."
        ),
        hint='Для сборки строки подойдет f"{target}:{port} secure={secure}".',
        advanced_hint="Проверь регистр: логическое значение пишется как True.",
        starter_code=(
            'target = "unknown"\n'
            "port = 0\n"
            "secure = False\n"
            'print(f"{target}:{port} secure={secure}")\n'
        ),
        bitcoins_reward=30,
        exp_reward=150,
        reward_item="target_dossier",
    ),
    Mission(
        mission_id="heartbeat",
        number=3,
        title="Heartbeat",
        difficulty="УСЛОВИЯ",
        briefing=(
            "Перед соединением нужно проверить узел. В песочнице доступен "
            "безопасный симулятор ping(host), который возвращает True или False."
        ),
        objective=(
            "Проверь cyberdeck.local через ping(). Если узел доступен, запиши "
            "ONLINE в status, иначе OFFLINE. Выведи status."
        ),
        hint="Используй конструкцию if ping(host): ... else: ...",
        advanced_hint="Внутри веток не забудь отступ в четыре пробела.",
        starter_code=(
            'host = "cyberdeck.local"\n'
            'status = "UNKNOWN"\n'
            "# Проверь host с помощью if/else.\n"
            "print(status)\n"
        ),
        bitcoins_reward=45,
        exp_reward=220,
        karma_reward=3,
        reward_item="network_map",
    ),
    Mission(
        mission_id="port_sweep",
        number=4,
        title="Port Sweep",
        difficulty="СПИСКИ",
        briefing=(
            "Узел отвечает. Теперь scan_ports(host) вернет список открытых "
            "портов. Из списка нужно выбрать стандартные web-порты."
        ),
        objective=(
            "Просканируй cyberdeck.local, сохрани результат в ports, а порты "
            "80 и 443 — в новом списке web_ports. Выведи web_ports."
        ),
        hint="Новый список можно собрать: [p for p in ports if p in (80, 443)].",
        advanced_hint="Ожидаемый web_ports: [80, 443].",
        starter_code=(
            'host = "cyberdeck.local"\n'
            "ports = []\n"
            "web_ports = []\n"
            "# Вызови scan_ports() и отфильтруй результат.\n"
            "print(web_ports)\n"
        ),
        bitcoins_reward=65,
        exp_reward=300,
        reward_item="port_scanner_v1",
    ),
    Mission(
        mission_id="pin_bruteforce",
        number=5,
        title="PIN Bruteforce",
        difficulty="ЦИКЛЫ",
        briefing=(
            "Учебный замок принимает PIN от 00 до 99. Проверка не раскрывает "
            "PIN напрямую, но верный кандидат дает checksum 1."
        ),
        objective=(
            "Перебери candidate через range(100). Найди число, для которого "
            "(candidate * 37) % 100 == 1, сохрани его в pin и выведи."
        ),
        hint="В цикле for проверяй checksum через if и присвой pin = candidate.",
        advanced_hint="После нахождения значения останови цикл командой break.",
        starter_code=(
            "pin = None\n"
            "for candidate in range(100):\n"
            "    checksum = (candidate * 37) % 100\n"
            "    # Сравни checksum с 1 и сохрани candidate.\n"
            "print(pin)\n"
        ),
        bitcoins_reward=90,
        exp_reward=420,
        karma_reward=-2,
        reward_item="pin_fragment",
    ),
    Mission(
        mission_id="log_parser",
        number=6,
        title="Log Parser",
        difficulty="СЛОВАРИ",
        briefing=(
            "В журнале авторизации перемешаны успешные и неуспешные входы. "
            "Аналитик считает ошибки по каждому IP с помощью словаря."
        ),
        objective=(
            'Создай failed_by_ip: посчитай записи со status == "failed". '
            "Должно получиться {'10.0.0.8': 2, '10.0.0.3': 1}."
        ),
        hint="Начни с failed_by_ip = {} и используй dict.get(ip, 0) + 1.",
        advanced_hint="Перебирай записи: for entry in logs: затем проверь entry['status'].",
        starter_code=(
            "logs = [\n"
            '    {"ip": "10.0.0.8", "status": "failed"},\n'
            '    {"ip": "10.0.0.2", "status": "ok"},\n'
            '    {"ip": "10.0.0.8", "status": "failed"},\n'
            '    {"ip": "10.0.0.3", "status": "failed"},\n'
            "]\n"
            "failed_by_ip = {}\n"
            "# Заполни словарь данными из logs.\n"
            "print(failed_by_ip)\n"
        ),
        bitcoins_reward=120,
        exp_reward=550,
        karma_reward=8,
        reward_item="forensic_log",
    ),
    Mission(
        mission_id="caesar_gate",
        number=7,
        title="Caesar Gate",
        difficulty="ШИФРЫ",
        briefing=(
            "Перехвачен текст DFFHVV JUDQWHG. API decrypt_caesar(text, shift) "
            "сдвигает буквы назад и сохраняет пробелы."
        ),
        objective=(
            "Расшифруй сообщение со сдвигом 3, сохрани его в plaintext и выведи."
        ),
        hint="plaintext = decrypt_caesar(ciphertext, 3)",
        advanced_hint="Правильный открытый текст начинается с ACCESS.",
        starter_code=(
            'ciphertext = "DFFHVV JUDQWHG"\n'
            "plaintext = decrypt_caesar(ciphertext, 0)\n"
            "print(plaintext)\n"
        ),
        bitcoins_reward=150,
        exp_reward=700,
        reward_item="cipher_key",
    ),
    Mission(
        mission_id="shift_hunter",
        number=8,
        title="Shift Hunter",
        difficulty="БРУТФОРС",
        briefing=(
            "Новый шифротекст пришел без ключа. Известно только, что исходное "
            "сообщение содержит маркер ACCESS."
        ),
        objective=(
            "Перебери shift от 0 до 25 для HJJLZZ AVRLU. Когда plaintext "
            "содержит ACCESS, сохрани shift в found_shift и выведи plaintext."
        ),
        hint='Цикл range(26) и условие if "ACCESS" in candidate_text решат задачу.',
        advanced_hint="Сохрани одновременно found_shift и plaintext, затем используй break.",
        starter_code=(
            'ciphertext = "HJJLZZ AVRLU"\n'
            "found_shift = None\n"
            'plaintext = ""\n'
            "# Перебери все сдвиги и найди текст с маркером ACCESS.\n"
            "print(plaintext)\n"
        ),
        bitcoins_reward=200,
        exp_reward=900,
        karma_reward=-3,
        reward_item="token_fragment",
    ),
    Mission(
        mission_id="json_exfil",
        number=9,
        title="JSON Exfil",
        difficulty="ПАРСИНГ",
        briefing=(
            "Сервис вернул JSON. Безопасный импорт json доступен в песочнице. "
            "Нужно извлечь активный узел и защищенный порт."
        ),
        objective=(
            "Разбери raw через json.loads(), сохрани словарь в data и создай "
            "endpoint со значением alpha:443. Выведи endpoint."
        ),
        hint="После json.loads(raw) используй data['node'] и data['ports'][1].",
        advanced_hint="endpoint удобно собрать через f-строку.",
        starter_code=(
            "import json\n"
            'raw = \'{"node":"alpha","ports":[22,443],"active":true}\'\n'
            "data = {}\n"
            'endpoint = ""\n'
            "# Разбери raw и собери endpoint.\n"
            "print(endpoint)\n"
        ),
        bitcoins_reward=260,
        exp_reward=1100,
        karma_reward=7,
        reward_item="zero_day_report",
    ),
    Mission(
        mission_id="grey_choice",
        number=10,
        title="The Grey Choice",
        difficulty="ФИНАЛ",
        briefing=(
            "Ты нашел критическую уязвимость Vault. Код должен отправить улику, "
            "а решение определит путь: report — белый, sell — серый, exploit — черный."
        ),
        objective=(
            "Установи decision в report, sell или exploit. Отправь строку "
            "evidence:root-access на vault.greyhat через send_payload() и сохрани "
            "ответ в receipt. Выведи decision и receipt['accepted']."
        ),
        hint="receipt = send_payload(target, evidence)",
        advanced_hint='Самый этичный выбор: decision = "report".',
        starter_code=(
            'target = "vault.greyhat"\n'
            'evidence = "evidence:root-access"\n'
            'decision = "observe"\n'
            "receipt = {}\n"
            "# Выбери путь и отправь evidence через send_payload().\n"
            'print(decision, receipt.get("accepted"))\n'
        ),
        bitcoins_reward=500,
        exp_reward=3600,
        reward_item="vault_master_key",
    ),
)

UPGRADES: Final[tuple[Upgrade, ...]] = (
    Upgrade(
        "neural_cache",
        "Neural Cache",
        "Показывает расширенную часть подсказки для каждой миссии.",
        120,
    ),
    Upgrade(
        "trace_shield",
        "Trace Shield",
        "Снижает потерю кармы при выборе черного пути.",
        180,
    ),
    Upgrade(
        "quantum_decoder",
        "Quantum Decoder",
        "Увеличивает лимит выполнения кода с 3 до 6 секунд.",
        280,
    ),
    Upgrade(
        "wallet_mixer",
        "Wallet Optimizer",
        "Увеличивает будущие награды в BTC на 20 процентов.",
        350,
    ),
)

MISSION_BY_ID: Final[Mapping[str, Mission]] = MappingProxyType(
    {mission.mission_id: mission for mission in MISSIONS}
)
UPGRADE_BY_ID: Final[Mapping[str, Upgrade]] = MappingProxyType(
    {upgrade.upgrade_id: upgrade for upgrade in UPGRADES}
)

SAVE_PATH: Final[Path] = Path.home() / ".greyhat_cyberdeck" / SAVE_FILE_NAME


def _load_customtkinter() -> Any:
    try:
        import customtkinter
    except ImportError as exc:
        raise RuntimeError(
            "CustomTkinter не установлен. Выполните: "
            "python -m pip install customtkinter>=5.2,<6"
        ) from exc
    return customtkinter


class GreyHatCyberdeck:
    """Desktop UI and gameplay controller for the offline campaign."""

    def __init__(self) -> None:
        self.ctk = _load_customtkinter()
        self.ctk.set_appearance_mode(APPEARANCE_MODE)
        self.ctk.set_default_color_theme(COLOR_THEME)

        self.root: Any = self.ctk.CTk()
        self.root.title(APP_NAME)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.root.configure(fg_color=DARK_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.state = self._load_state()
        self._normalize_mission_progress()
        self.current_mission_id: str | None = None
        self.code_buffers: dict[str, str] = {}
        self.mission_buttons: dict[str, Any] = {}
        self._running = False
        self._closing = False

        self.stats_label: Any = None
        self.path_label: Any = None
        self.progress_bar: Any = None
        self.progress_label: Any = None
        self.mission_title_label: Any = None
        self.mission_meta_label: Any = None
        self.briefing_box: Any = None
        self.objective_label: Any = None
        self.editor: Any = None
        self.terminal: Any = None
        self.command_entry: Any = None
        self.run_button: Any = None
        self.status_label: Any = None

        self._build_interface()
        self._refresh_all()
        self._select_initial_mission()
        self.root.bind("<F5>", lambda _event: self._run_code())
        self.root.bind("<Control-s>", lambda _event: self._save_game(show_message=True))
        self.root.after(250, self._boot_message)
        self.root.after(AUTOSAVE_INTERVAL_MS, self._autosave_tick)

    def _load_state(self) -> GameState:
        if not SAVE_PATH.exists():
            return GameState()
        try:
            return GameState.load(SAVE_PATH)
        except GameStateError:
            backup = SAVE_PATH.with_suffix(".broken.json")
            try:
                SAVE_PATH.replace(backup)
            except OSError:
                backup = SAVE_PATH
            print(f"Поврежденное сохранение оставлено в {backup}", file=sys.stderr)
            return GameState()

    def _normalize_mission_progress(self) -> None:
        for mission in MISSIONS:
            if mission.mission_id not in self.state.missions:
                self.state.missions[mission.mission_id] = MissionStatus.LOCKED
        first = MISSIONS[0]
        if self.state.get_mission_status(first.mission_id) is MissionStatus.LOCKED:
            self.state.set_mission_status(first.mission_id, MissionStatus.AVAILABLE)
        for index, mission in enumerate(MISSIONS[:-1]):
            if (
                self.state.get_mission_status(mission.mission_id)
                is MissionStatus.COMPLETED
            ):
                next_id = MISSIONS[index + 1].mission_id
                if self.state.get_mission_status(next_id) is MissionStatus.LOCKED:
                    self.state.set_mission_status(next_id, MissionStatus.AVAILABLE)

    def _build_interface(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self._build_topbar()
        self._build_main_area()

    def _build_topbar(self) -> None:
        topbar = self.ctk.CTkFrame(
            self.root,
            height=68,
            corner_radius=0,
            fg_color=DARK_GRAY,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_columnconfigure(1, weight=1)

        brand = self.ctk.CTkLabel(
            topbar,
            text="GREYHAT // CYBERDECK OS",
            font=FONT_TITLE,
            text_color=NEON_GREEN,
        )
        brand.grid(row=0, column=0, padx=(24, 12), pady=17, sticky="w")

        self.status_label = self.ctk.CTkLabel(
            topbar,
            text="SANDBOX: READY",
            font=FONT_SMALL,
            text_color=ACCENT_CYAN,
        )
        self.status_label.grid(row=0, column=1, padx=12)

        self.path_label = self.ctk.CTkLabel(
            topbar,
            text="",
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
        )
        self.path_label.grid(row=0, column=2, padx=12)

        self.stats_label = self.ctk.CTkLabel(
            topbar,
            text="",
            font=FONT_HEADING,
            text_color=TEXT_PRIMARY,
        )
        self.stats_label.grid(row=0, column=3, padx=(12, 24), sticky="e")

    def _build_main_area(self) -> None:
        body = self.ctk.CTkFrame(self.root, fg_color=DARK_BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=12)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)

        self._build_sidebar(body)
        self._build_workspace(body)

    def _build_sidebar(self, parent: Any) -> None:
        sidebar = self.ctk.CTkFrame(
            parent,
            width=285,
            fg_color=DARK_GRAY,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(2, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        heading = self.ctk.CTkLabel(
            sidebar,
            text="MISSION QUEUE",
            font=FONT_HEADING,
            text_color=ACCENT_CYAN,
        )
        heading.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        progress_frame = self.ctk.CTkFrame(sidebar, fg_color="transparent")
        progress_frame.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_label = self.ctk.CTkLabel(
            progress_frame, text="", font=FONT_SMALL, text_color=TEXT_MUTED
        )
        self.progress_label.grid(row=0, column=0, sticky="w")
        self.progress_bar = self.ctk.CTkProgressBar(
            progress_frame,
            height=8,
            progress_color=NEON_GREEN,
            fg_color=DARK_BG,
        )
        self.progress_bar.grid(row=1, column=0, pady=(5, 0), sticky="ew")

        mission_list = self.ctk.CTkScrollableFrame(
            sidebar,
            fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=ACCENT_CYAN,
        )
        mission_list.grid(row=2, column=0, padx=8, pady=4, sticky="nsew")
        mission_list.grid_columnconfigure(0, weight=1)

        for row, mission in enumerate(MISSIONS):
            button = self.ctk.CTkButton(
                mission_list,
                text="",
                height=46,
                anchor="w",
                font=FONT_SMALL,
                fg_color=DARK_BG,
                hover_color=BORDER_COLOR,
                border_width=1,
                border_color=BORDER_COLOR,
                command=lambda mission_id=mission.mission_id: self._select_mission(
                    mission_id
                ),
            )
            button.grid(row=row, column=0, padx=3, pady=4, sticky="ew")
            self.mission_buttons[mission.mission_id] = button

        actions = self.ctk.CTkFrame(sidebar, fg_color="transparent")
        actions.grid(row=3, column=0, padx=12, pady=12, sticky="ew")
        actions.grid_columnconfigure((0, 1), weight=1)
        self.ctk.CTkButton(
            actions,
            text="DARKNET",
            fg_color="#102A20",
            hover_color="#16452F",
            text_color=NEON_GREEN,
            border_width=1,
            border_color=NEON_GREEN,
            command=self._open_darknet,
        ).grid(row=0, column=0, padx=(0, 4), pady=3, sticky="ew")
        self.ctk.CTkButton(
            actions,
            text="INVENTORY",
            fg_color="#10232A",
            hover_color="#153944",
            text_color=ACCENT_CYAN,
            border_width=1,
            border_color=ACCENT_CYAN,
            command=self._open_inventory,
        ).grid(row=0, column=1, padx=(4, 0), pady=3, sticky="ew")
        self.ctk.CTkButton(
            actions,
            text="RESET PROGRESS",
            fg_color="transparent",
            hover_color="#421926",
            text_color=WARNING_RED,
            border_width=1,
            border_color=WARNING_RED,
            command=self._reset_progress,
        ).grid(row=1, column=0, columnspan=2, pady=(6, 0), sticky="ew")

    def _build_workspace(self, parent: Any) -> None:
        workspace = self.ctk.CTkFrame(parent, fg_color=DARK_BG, corner_radius=0)
        workspace.grid(row=0, column=1, sticky="nsew")
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_rowconfigure(3, weight=3)
        workspace.grid_rowconfigure(5, weight=2)

        title_frame = self.ctk.CTkFrame(workspace, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        title_frame.grid_columnconfigure(0, weight=1)
        self.mission_title_label = self.ctk.CTkLabel(
            title_frame, text="", font=FONT_TITLE, text_color=TEXT_PRIMARY
        )
        self.mission_title_label.grid(row=0, column=0, sticky="w")
        self.mission_meta_label = self.ctk.CTkLabel(
            title_frame, text="", font=FONT_SMALL, text_color=ACCENT_CYAN
        )
        self.mission_meta_label.grid(row=0, column=1, sticky="e")

        briefing_frame = self.ctk.CTkFrame(
            workspace,
            fg_color=DARK_GRAY,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        briefing_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        briefing_frame.grid_columnconfigure(0, weight=1)
        self.briefing_box = self.ctk.CTkTextbox(
            briefing_frame,
            height=78,
            wrap="word",
            activate_scrollbars=False,
            fg_color="transparent",
            text_color=TEXT_PRIMARY,
            font=FONT_BODY,
        )
        self.briefing_box.grid(row=0, column=0, padx=10, pady=(8, 2), sticky="ew")
        self.objective_label = self.ctk.CTkLabel(
            briefing_frame,
            text="",
            wraplength=900,
            justify="left",
            anchor="w",
            font=FONT_BODY,
            text_color=NEON_GREEN,
        )
        self.objective_label.grid(row=1, column=0, padx=16, pady=(2, 10), sticky="ew")

        editor_header = self.ctk.CTkFrame(workspace, fg_color="transparent")
        editor_header.grid(row=2, column=0, sticky="ew")
        editor_header.grid_columnconfigure(0, weight=1)
        self.ctk.CTkLabel(
            editor_header,
            text="PYTHON EDITOR // mission.py",
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
        ).grid(row=0, column=0, sticky="w")
        self.ctk.CTkLabel(
            editor_header,
            text="F5 — RUN    Ctrl+S — SAVE",
            font=FONT_SMALL,
            text_color=TEXT_MUTED,
        ).grid(row=0, column=1, sticky="e")

        self.editor = self.ctk.CTkTextbox(
            workspace,
            undo=True,
            wrap="none",
            font=FONT_CODE,
            fg_color="#090D12",
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color=BORDER_COLOR,
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=ACCENT_CYAN,
        )
        self.editor.grid(row=3, column=0, sticky="nsew", pady=(5, 8))

        controls = self.ctk.CTkFrame(workspace, fg_color="transparent")
        controls.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        controls.grid_columnconfigure(3, weight=1)
        self.run_button = self.ctk.CTkButton(
            controls,
            text="> RUN CODE",
            width=150,
            font=FONT_HEADING,
            fg_color=NEON_GREEN,
            hover_color="#00C853",
            text_color=DARK_BG,
            command=self._run_code,
        )
        self.run_button.grid(row=0, column=0, padx=(0, 8))
        self.ctk.CTkButton(
            controls,
            text="HINT",
            width=100,
            fg_color="transparent",
            hover_color="#12343B",
            border_width=1,
            border_color=ACCENT_CYAN,
            text_color=ACCENT_CYAN,
            command=self._show_hint,
        ).grid(row=0, column=1, padx=4)
        self.ctk.CTkButton(
            controls,
            text="RESET CODE",
            width=110,
            fg_color="transparent",
            hover_color=BORDER_COLOR,
            border_width=1,
            border_color=TEXT_MUTED,
            text_color=TEXT_MUTED,
            command=self._reset_code,
        ).grid(row=0, column=2, padx=4)

        terminal_frame = self.ctk.CTkFrame(
            workspace,
            fg_color="#070B0F",
            border_width=1,
            border_color=BORDER_COLOR,
        )
        terminal_frame.grid(row=5, column=0, sticky="nsew")
        terminal_frame.grid_columnconfigure(0, weight=1)
        terminal_frame.grid_rowconfigure(1, weight=1)
        self.ctk.CTkLabel(
            terminal_frame,
            text=" CYBERDECK TERMINAL",
            font=FONT_SMALL,
            text_color=NEON_GREEN,
            anchor="w",
        ).grid(row=0, column=0, padx=8, pady=(5, 0), sticky="ew")
        self.terminal = self.ctk.CTkTextbox(
            terminal_frame,
            height=180,
            wrap="word",
            font=FONT_TERMINAL,
            fg_color="transparent",
            text_color=NEON_GREEN,
            activate_scrollbars=True,
        )
        self.terminal.grid(row=1, column=0, padx=6, pady=3, sticky="nsew")
        self.terminal.configure(state="disabled")

        command_row = self.ctk.CTkFrame(terminal_frame, fg_color="transparent")
        command_row.grid(row=2, column=0, padx=8, pady=(0, 7), sticky="ew")
        command_row.grid_columnconfigure(1, weight=1)
        self.ctk.CTkLabel(
            command_row,
            text="deck$",
            font=FONT_TERMINAL,
            text_color=ACCENT_CYAN,
        ).grid(row=0, column=0, padx=(0, 6))
        self.command_entry = self.ctk.CTkEntry(
            command_row,
            border_width=0,
            fg_color=DARK_BG,
            text_color=TEXT_PRIMARY,
            font=FONT_TERMINAL,
            placeholder_text="help",
        )
        self.command_entry.grid(row=0, column=1, sticky="ew")
        self.command_entry.bind("<Return>", self._handle_terminal_command)

    def _boot_message(self) -> None:
        self._terminal_write("GreyHat Cyberdeck OS initialized.", "SYS")
        self._terminal_write(
            "Sandbox online. Real network and filesystem are isolated.", "SEC"
        )
        self._terminal_write("Type 'help' for local terminal commands.", "SYS")

    def _select_initial_mission(self) -> None:
        candidate = MISSIONS[0]
        for mission in MISSIONS:
            status = self.state.get_mission_status(mission.mission_id)
            if status in (MissionStatus.AVAILABLE, MissionStatus.IN_PROGRESS):
                candidate = mission
                break
            if status is not MissionStatus.COMPLETED:
                candidate = mission
                break
        self._select_mission(candidate.mission_id)

    def _select_mission(self, mission_id: str) -> None:
        mission = MISSION_BY_ID[mission_id]
        status = self.state.get_mission_status(mission_id)
        if status is MissionStatus.LOCKED:
            self._terminal_write(
                f"Mission {mission.number:02d} is locked. Complete the previous node.",
                "LOCK",
            )
            return

        if self.current_mission_id is not None:
            self.code_buffers[self.current_mission_id] = self.editor.get(
                "1.0", "end-1c"
            )
        self.current_mission_id = mission_id
        if status is MissionStatus.AVAILABLE:
            self.state.set_mission_status(mission_id, MissionStatus.IN_PROGRESS)

        self.mission_title_label.configure(
            text=f"{mission.number:02d} // {mission.title}"
        )
        self.mission_meta_label.configure(
            text=f"{mission.difficulty}   +{mission.bitcoins_reward} BTC   +{mission.exp_reward} EXP"
        )
        self._set_readonly_text(self.briefing_box, mission.briefing)
        self.objective_label.configure(text=f"OBJECTIVE: {mission.objective}")
        self.editor.delete("1.0", "end")
        self.editor.insert(
            "1.0", self.code_buffers.get(mission_id, mission.starter_code)
        )
        self._refresh_navigation()
        self._save_game(show_message=False)

    @staticmethod
    def _set_readonly_text(widget: Any, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _run_code(self) -> None:
        if self._running or self.current_mission_id is None:
            return
        source = self.editor.get("1.0", "end-1c")
        if not source.strip():
            self._terminal_write("Editor is empty.", "ERR")
            return

        mission = MISSION_BY_ID[self.current_mission_id]
        self.code_buffers[mission.mission_id] = source
        self._running = True
        self.run_button.configure(state="disabled", text="RUNNING...")
        self.status_label.configure(text="SANDBOX: EXECUTING", text_color=WARNING_RED)
        self._terminal_write(
            f"Executing mission {mission.number:02d} in isolated process...", "RUN"
        )
        worker = threading.Thread(
            target=self._execute_in_background,
            args=(mission, source),
            daemon=True,
            name="CyberdeckRunner",
        )
        worker.start()

    def _execute_in_background(self, mission: Mission, source: str) -> None:
        timeout = 6.0 if "quantum_decoder" in self.state.purchased_upgrades else 3.0
        result = Sandbox(timeout=timeout).execute(source)
        if self._closing:
            return
        try:
            self.root.after(0, lambda: self._finish_execution(mission, result))
        except Exception:
            return

    def _finish_execution(self, mission: Mission, result: SandboxResult) -> None:
        self._running = False
        self.run_button.configure(state="normal", text="> RUN CODE")
        self.status_label.configure(text="SANDBOX: READY", text_color=ACCENT_CYAN)

        if result.output:
            for line in result.output.rstrip("\n").splitlines():
                self._terminal_write(line, "OUT")
        if result.stderr:
            for line in result.stderr.rstrip("\n").splitlines():
                self._terminal_write(line, "STDERR")
        if not result.success:
            self._terminal_write(result.error or "Unknown sandbox error", "ERR")
            if result.timed_out:
                self._terminal_write("Check for an infinite loop.", "TIP")
            return

        solved, feedback, choice_karma = self._check_solution(mission, result)
        if not solved:
            self._terminal_write(feedback, "DENIED")
            self._terminal_write(
                "Code executed safely, but the objective is not met yet.", "TIP"
            )
            return
        self._terminal_write(feedback, "ACCEPT")
        self._complete_mission(mission, choice_karma)

    @staticmethod
    def _check_solution(
        mission: Mission, result: SandboxResult
    ) -> tuple[bool, str, int]:
        variables = result.variables
        output = result.output.strip()
        mission_id = mission.mission_id

        if mission_id == "boot_protocol":
            ok = variables.get("handle") == "ghost" and output == "ACCESS: ghost"
            return (
                ok,
                "Identity accepted."
                if ok
                else "Expected handle='ghost' and exact output ACCESS: ghost.",
                0,
            )

        if mission_id == "target_profile":
            ok = (
                variables.get("target") == "vault.greyhat"
                and type(variables.get("port")) is int
                and variables.get("port") == 443
                and variables.get("secure") is True
                and output == "vault.greyhat:443 secure=True"
            )
            return (
                ok,
                "Target profile loaded."
                if ok
                else "Check target, port, secure and the output format.",
                0,
            )

        if mission_id == "heartbeat":
            ok = (
                variables.get("host") == "cyberdeck.local"
                and variables.get("status") == "ONLINE"
                and output == "ONLINE"
            )
            return (
                ok,
                "Heartbeat confirmed."
                if ok
                else "Use ping(host) and store ONLINE in status.",
                0,
            )

        if mission_id == "port_sweep":
            ok = (
                variables.get("ports") == [22, 80, 443, 31337]
                and variables.get("web_ports") == [80, 443]
                and output == "[80, 443]"
            )
            return (
                ok,
                "Web surface mapped."
                if ok
                else "ports must come from scan_ports(); web_ports must contain 80 and 443 and be printed.",
                0,
            )

        if mission_id == "pin_bruteforce":
            ok = (
                type(variables.get("pin")) is int
                and variables.get("pin") == 73
                and output == "73"
            )
            return (
                ok,
                "PIN 73 cracked by iteration."
                if ok
                else "The valid candidate satisfies (candidate * 37) % 100 == 1; store and print it.",
                0,
            )

        if mission_id == "log_parser":
            expected = {"10.0.0.8": 2, "10.0.0.3": 1}
            ok = variables.get("failed_by_ip") == expected
            return (
                ok,
                "Failed logins aggregated."
                if ok
                else f"Expected failed_by_ip = {expected!r}.",
                0,
            )

        if mission_id == "caesar_gate":
            ok = (
                variables.get("plaintext") == "ACCESS GRANTED"
                and output == "ACCESS GRANTED"
            )
            return (
                ok,
                "Caesar gate decrypted."
                if ok
                else "Decrypt ciphertext with shift 3 and print plaintext.",
                0,
            )

        if mission_id == "shift_hunter":
            ok = (
                variables.get("found_shift") == 7
                and variables.get("plaintext") == "ACCESS TOKEN"
                and output == "ACCESS TOKEN"
            )
            return (
                ok,
                "Shift 7 and token recovered."
                if ok
                else "Try every shift in range(26), search for ACCESS and print plaintext.",
                0,
            )

        if mission_id == "json_exfil":
            data = variables.get("data")
            ok = (
                data == {"node": "alpha", "ports": [22, 443], "active": True}
                and variables.get("endpoint") == "alpha:443"
                and output == "alpha:443"
            )
            return (
                ok,
                "JSON endpoint extracted."
                if ok
                else "Parse raw with json.loads() and build alpha:443.",
                0,
            )

        if mission_id == "grey_choice":
            decision = variables.get("decision")
            expected_receipt = send_payload("vault.greyhat", "evidence:root-access")
            receipt = variables.get("receipt")
            ok = (
                decision in {"report", "sell", "exploit"}
                and receipt == expected_receipt
                and output == f"{decision} True"
            )
            karma_by_choice = {"report": 30, "sell": 0, "exploit": -50}
            if not ok:
                return (
                    False,
                    "Choose report, sell or exploit and store the real send_payload() receipt.",
                    0,
                )
            return (
                True,
                f"Vault evidence delivered. Decision locked: {decision}.",
                karma_by_choice[str(decision)],
            )

        return False, "Unknown mission validator.", 0

    def _complete_mission(self, mission: Mission, choice_karma: int) -> None:
        already_completed = (
            self.state.get_mission_status(mission.mission_id) is MissionStatus.COMPLETED
        )
        if already_completed:
            self._terminal_write(
                "Mission already completed; no duplicate reward.", "SYS"
            )
            return

        reward_btc = mission.bitcoins_reward
        if "wallet_mixer" in self.state.purchased_upgrades:
            reward_btc = round(reward_btc * 1.2)
        karma_delta = mission.karma_reward + choice_karma
        if karma_delta < 0 and "trace_shield" in self.state.purchased_upgrades:
            karma_delta = min(-1, karma_delta // 2)

        self.state.complete_mission(
            mission.mission_id,
            bitcoins_reward=reward_btc,
            exp_reward=mission.exp_reward,
            karma_delta=karma_delta,
        )
        if mission.reward_item is not None:
            self.state.add_item(mission.reward_item)

        mission_index = MISSIONS.index(mission)
        if mission_index + 1 < len(MISSIONS):
            next_mission = MISSIONS[mission_index + 1]
            if (
                self.state.get_mission_status(next_mission.mission_id)
                is MissionStatus.LOCKED
            ):
                self.state.set_mission_status(
                    next_mission.mission_id, MissionStatus.AVAILABLE
                )
            self._terminal_write(
                f"Unlocked mission {next_mission.number:02d}: {next_mission.title}",
                "UNLOCK",
            )
        else:
            self._show_ending()

        self._terminal_write(
            f"Reward: +{reward_btc} BTC, +{mission.exp_reward} EXP, karma {karma_delta:+d}",
            "REWARD",
        )
        self._save_game(show_message=False)
        self._refresh_all()

    def _show_ending(self) -> None:
        path = self.state.karma_path
        endings = {
            KarmaPath.WHITE: "WHITE HAT ENDING // Ты передал уязвимость и защитил сеть.",
            KarmaPath.GREY: "GREY HAT ENDING // Ты сохранил баланс между законом и свободой.",
            KarmaPath.BLACK: "BLACK HAT ENDING // Сеть знает тебя как цифрового призрака.",
        }
        self._terminal_write("=" * 58, "SYS")
        self._terminal_write(endings[path], "ENDING")
        self._terminal_write(
            "Campaign complete. Missions remain available for practice.", "SYS"
        )

    def _show_hint(self) -> None:
        if self.current_mission_id is None:
            return
        mission = MISSION_BY_ID[self.current_mission_id]
        self._terminal_write(mission.hint, "HINT")
        if "neural_cache" in self.state.purchased_upgrades:
            self._terminal_write(mission.advanced_hint, "CACHE")

    def _reset_code(self) -> None:
        if self.current_mission_id is None:
            return
        mission = MISSION_BY_ID[self.current_mission_id]
        self.code_buffers.pop(mission.mission_id, None)
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", mission.starter_code)
        self._terminal_write("Editor restored to mission starter code.", "SYS")

    def _handle_terminal_command(self, _event: Any = None) -> None:
        command = self.command_entry.get().strip()
        self.command_entry.delete(0, "end")
        if not command:
            return
        self._terminal_write(f"deck$ {command}", "CMD")
        parts = command.split()
        action = parts[0].lower()

        commands: Mapping[str, Callable[[], None]] = {
            "help": self._terminal_help,
            "status": self._terminal_status,
            "missions": self._terminal_missions,
            "clear": self._terminal_clear,
            "hint": self._show_hint,
            "run": self._run_code,
            "inventory": self._open_inventory,
            "darknet": self._open_darknet,
            "save": lambda: self._save_game(show_message=True),
        }
        handler = commands.get(action)
        if handler is not None and len(parts) == 1:
            handler()
            return
        if action == "mission" and len(parts) == 2:
            self._terminal_select_mission(parts[1])
            return
        if action == "scan" and len(parts) == 2:
            try:
                ports = scan_ports(parts[1])
            except (TypeError, ValueError) as exc:
                self._terminal_write(str(exc), "ERR")
            else:
                self._terminal_write(f"simulated open ports: {ports}", "SCAN")
            return
        self._terminal_write("Unknown command. Type help.", "ERR")

    def _terminal_help(self) -> None:
        self._terminal_write(
            "Commands: help, status, missions, mission <01-10>, run, hint, "
            "scan <host>, inventory, darknet, save, clear",
            "HELP",
        )

    def _terminal_status(self) -> None:
        self._terminal_write(
            f"rank={self.state.rank.value} exp={self.state.exp} "
            f"btc={self.state.bitcoins} karma={self.state.karma} "
            f"path={self.state.karma_path.value}",
            "STATUS",
        )

    def _terminal_missions(self) -> None:
        for mission in MISSIONS:
            status = self.state.get_mission_status(mission.mission_id).value
            self._terminal_write(
                f"{mission.number:02d} {status:11s} {mission.title}", "MISSION"
            )

    def _terminal_select_mission(self, token: str) -> None:
        try:
            number = int(token)
        except ValueError:
            self._terminal_write("Mission number must be 01-10.", "ERR")
            return
        for mission in MISSIONS:
            if mission.number == number:
                self._select_mission(mission.mission_id)
                return
        self._terminal_write("Mission number must be 01-10.", "ERR")

    def _terminal_clear(self) -> None:
        self.terminal.configure(state="normal")
        self.terminal.delete("1.0", "end")
        self.terminal.configure(state="disabled")

    def _terminal_write(self, message: str, channel: str = "SYS") -> None:
        if self.terminal is None:
            return
        safe_message = str(message).replace("\r", "")
        self.terminal.configure(state="normal")
        self.terminal.insert("end", f"[{channel}] {safe_message}\n")
        line_count = int(self.terminal.index("end-1c").split(".")[0])
        if line_count > MAX_TERMINAL_LINES:
            remove_count = line_count - MAX_TERMINAL_LINES
            self.terminal.delete("1.0", f"{remove_count + 1}.0")
        self.terminal.see("end")
        self.terminal.configure(state="disabled")

    def _open_darknet(self) -> None:
        window = self.ctk.CTkToplevel(self.root)
        window.title("DarkNet // Upgrades")
        window.geometry("620x560")
        window.configure(fg_color=DARK_BG)
        window.transient(self.root)
        window.grab_set()
        window.grid_columnconfigure(0, weight=1)

        self.ctk.CTkLabel(
            window,
            text="DARKNET MARKET",
            font=FONT_TITLE,
            text_color=NEON_GREEN,
        ).grid(row=0, column=0, padx=22, pady=(20, 5), sticky="w")
        balance_label = self.ctk.CTkLabel(
            window,
            text=f"WALLET: {self.state.bitcoins} BTC",
            font=FONT_HEADING,
            text_color=ACCENT_CYAN,
        )
        balance_label.grid(row=1, column=0, padx=22, pady=(0, 12), sticky="w")

        market = self.ctk.CTkScrollableFrame(window, fg_color="transparent")
        market.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")
        window.grid_rowconfigure(2, weight=1)
        market.grid_columnconfigure(0, weight=1)

        for row, upgrade in enumerate(UPGRADES):
            card = self.ctk.CTkFrame(
                market,
                fg_color=DARK_GRAY,
                border_width=1,
                border_color=BORDER_COLOR,
            )
            card.grid(row=row, column=0, padx=4, pady=6, sticky="ew")
            card.grid_columnconfigure(0, weight=1)
            self.ctk.CTkLabel(
                card,
                text=upgrade.title,
                font=FONT_HEADING,
                text_color=TEXT_PRIMARY,
                anchor="w",
            ).grid(row=0, column=0, padx=14, pady=(10, 2), sticky="ew")
            self.ctk.CTkLabel(
                card,
                text=upgrade.description,
                font=FONT_SMALL,
                text_color=TEXT_MUTED,
                wraplength=400,
                justify="left",
                anchor="w",
            ).grid(row=1, column=0, padx=14, pady=(2, 10), sticky="ew")

            purchased = upgrade.upgrade_id in self.state.purchased_upgrades
            buy_button = self.ctk.CTkButton(
                card,
                text="INSTALLED" if purchased else f"BUY {upgrade.price} BTC",
                width=125,
                fg_color=BORDER_COLOR if purchased else NEON_GREEN,
                hover_color="#00C853",
                text_color=TEXT_MUTED if purchased else DARK_BG,
                state="disabled" if purchased else "normal",
            )
            buy_button.configure(
                command=lambda upgrade_id=upgrade.upgrade_id,
                button=buy_button: self._buy_upgrade(upgrade_id, button, balance_label)
            )
            buy_button.grid(row=0, column=1, rowspan=2, padx=14, pady=12)

    def _buy_upgrade(self, upgrade_id: str, button: Any, balance_label: Any) -> None:
        upgrade = UPGRADE_BY_ID[upgrade_id]
        try:
            purchased = self.state.purchase_upgrade(upgrade_id, upgrade.price)
        except InsufficientFundsError as exc:
            self._terminal_write(str(exc), "DARKNET")
            return
        if not purchased:
            return
        button.configure(
            text="INSTALLED",
            state="disabled",
            fg_color=BORDER_COLOR,
            text_color=TEXT_MUTED,
        )
        balance_label.configure(text=f"WALLET: {self.state.bitcoins} BTC")
        self._terminal_write(f"Upgrade installed: {upgrade.title}", "DARKNET")
        self._save_game(show_message=False)
        self._refresh_stats()

    def _open_inventory(self) -> None:
        window = self.ctk.CTkToplevel(self.root)
        window.title("Cyberdeck // Inventory")
        window.geometry("520x470")
        window.configure(fg_color=DARK_BG)
        window.transient(self.root)
        window.grab_set()
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)

        self.ctk.CTkLabel(
            window,
            text="INVENTORY",
            font=FONT_TITLE,
            text_color=ACCENT_CYAN,
        ).grid(row=0, column=0, padx=22, pady=20, sticky="w")
        box = self.ctk.CTkTextbox(
            window,
            font=FONT_TERMINAL,
            fg_color=DARK_GRAY,
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        box.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        if self.state.inventory:
            for item_id, quantity in sorted(self.state.inventory.items()):
                box.insert("end", f"[ITEM] {item_id:<28} x{quantity}\n")
        else:
            box.insert(
                "end", "Inventory is empty. Complete missions to obtain artifacts.\n"
            )
        box.insert("end", "\n[UPGRADES]\n")
        if self.state.purchased_upgrades:
            for upgrade_id in sorted(self.state.purchased_upgrades):
                title = UPGRADE_BY_ID.get(
                    upgrade_id, Upgrade(upgrade_id, upgrade_id, "", 0)
                ).title
                box.insert("end", f"[INSTALLED] {title}\n")
        else:
            box.insert("end", "No upgrades installed.\n")
        box.configure(state="disabled")

    def _refresh_all(self) -> None:
        self._refresh_stats()
        self._refresh_navigation()

    def _refresh_stats(self) -> None:
        self.stats_label.configure(
            text=f"{self.state.bitcoins} BTC  //  {self.state.exp} EXP  //  {self.state.rank.value}"
        )
        karma_color = {
            KarmaPath.WHITE: ACCENT_CYAN,
            KarmaPath.GREY: TEXT_MUTED,
            KarmaPath.BLACK: WARNING_RED,
        }[self.state.karma_path]
        self.path_label.configure(
            text=f"KARMA {self.state.karma:+d} // {self.state.karma_path.value.upper()} PATH",
            text_color=karma_color,
        )

    def _refresh_navigation(self) -> None:
        completed = sum(
            self.state.get_mission_status(mission.mission_id) is MissionStatus.COMPLETED
            for mission in MISSIONS
        )
        self.progress_label.configure(text=f"PROGRESS {completed}/{len(MISSIONS)}")
        self.progress_bar.set(completed / len(MISSIONS))

        for mission in MISSIONS:
            status = self.state.get_mission_status(mission.mission_id)
            marker = {
                MissionStatus.LOCKED: "[ ]",
                MissionStatus.AVAILABLE: "[>]",
                MissionStatus.IN_PROGRESS: "[*]",
                MissionStatus.COMPLETED: "[+]",
                MissionStatus.FAILED: "[!]",
            }[status]
            selected = mission.mission_id == self.current_mission_id
            if selected:
                fg_color = "#12352A"
                border_color = NEON_GREEN
                text_color = NEON_GREEN
            elif status is MissionStatus.COMPLETED:
                fg_color = "#101D17"
                border_color = "#245A3A"
                text_color = "#72D99B"
            elif status is MissionStatus.LOCKED:
                fg_color = DARK_BG
                border_color = BORDER_COLOR
                text_color = "#59616B"
            else:
                fg_color = DARK_BG
                border_color = ACCENT_CYAN
                text_color = TEXT_PRIMARY
            self.mission_buttons[mission.mission_id].configure(
                text=f"{marker} {mission.number:02d}  {mission.title}",
                fg_color=fg_color,
                border_color=border_color,
                text_color=text_color,
            )

    def _save_game(self, *, show_message: bool) -> None:
        try:
            self.state.save(SAVE_PATH)
        except GameStateError as exc:
            self._terminal_write(str(exc), "SAVE")
            return
        if show_message:
            self._terminal_write(f"Progress saved to {SAVE_PATH}", "SAVE")

    def _autosave_tick(self) -> None:
        if self._closing:
            return
        self._save_game(show_message=False)
        self.root.after(AUTOSAVE_INTERVAL_MS, self._autosave_tick)

    def _reset_progress(self) -> None:
        try:
            from tkinter import messagebox
        except ImportError:
            self._terminal_write("Tk messagebox is unavailable.", "ERR")
            return
        confirmed = messagebox.askyesno(
            "Reset GreyHat",
            "Удалить весь прогресс, BTC, улучшения и инвентарь?",
            parent=self.root,
        )
        if not confirmed:
            return
        self.state = GameState()
        self.code_buffers.clear()
        self.current_mission_id = None
        self._normalize_mission_progress()
        try:
            SAVE_PATH.unlink(missing_ok=True)
        except OSError as exc:
            self._terminal_write(f"Could not delete save: {exc}", "ERR")
        self._refresh_all()
        self._terminal_clear()
        self._boot_message()
        self._select_initial_mission()
        self._save_game(show_message=False)

    def _on_close(self) -> None:
        self._closing = True
        self._save_game(show_message=False)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    try:
        app = GreyHatCyberdeck()
    except RuntimeError as exc:
        print(f"GreyHat startup error: {exc}", file=sys.stderr)
        return 1
    app.run()
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
