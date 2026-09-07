"""Базовая конфигурация GreyHat: Python Cyberdeck.

Модуль не зависит от GUI и может безопасно импортироваться до инициализации
CustomTkinter. Все пути вычисляются относительно каталога проекта.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final, Mapping


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
