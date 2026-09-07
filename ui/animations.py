"""Reusable ``after()``-driven visual effects for GreyHat Cyberdeck OS.

The classes in this module never sleep and never update Tk widgets from worker
threads.  Every animation step is scheduled on the widget that owns the effect,
which keeps CustomTkinter's event loop responsive.
"""

from __future__ import annotations

import math
import random
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import customtkinter as ctk

from config import (
    ACCENT_CYAN,
    BORDER_COLOR,
    DARK_BG,
    FONT_MONO_FAMILY,
    NEON_GREEN,
    TEXT_PRIMARY,
    WARNING_RED,
)

AnimationCallback = Callable[[], None]

_GLITCH_SYMBOLS: Final[str] = "░▒▓█▄▀"
_NOTIFICATION_STYLES: Final[dict[str, tuple[str, str]]] = {
    "success": (NEON_GREEN, "✓"),
    "danger": (WARNING_RED, "!"),
    "info": (ACCENT_CYAN, "i"),
}
_HACK_PHRASES: Final[tuple[str, ...]] = (
    "Компиляция payload...",
    "Поиск поверхности атаки...",
    "Синхронизация прокси-цепочки...",
    "Внедрение эксплойта...",
    "Подмена сигнатуры пакета...",
    "Обход файрвола...",
    "Очистка цифрового следа...",
    "Проверка контрольной суммы...",
)


def _widget_exists(widget: Any) -> bool:
    try:
        return bool(widget.winfo_exists())
    except (AttributeError, tk.TclError):
        return True


def _after(widget: Any, delay: int, callback: AnimationCallback) -> str:
    try:
        return str(widget.after(max(0, delay), callback))
    except (AttributeError, tk.TclError) as exc:
        raise RuntimeError("Виджет не поддерживает tkinter.after()") from exc


def _cancel_after(widget: Any, job: str | None) -> None:
    if job is None:
        return
    try:
        widget.after_cancel(job)
    except (AttributeError, tk.TclError):
        return


def _coerce_hex(color: object, widget: Any, fallback: str = DARK_BG) -> str:
    candidate: object = color
    if isinstance(candidate, (tuple, list)) and candidate:
        mode = ctk.get_appearance_mode().lower()
        candidate = (
            candidate[1] if mode == "dark" and len(candidate) > 1 else candidate[0]
        )
    if isinstance(candidate, str) and len(candidate) == 7 and candidate.startswith("#"):
        try:
            int(candidate[1:], 16)
        except ValueError:
            candidate = fallback
        else:
            return candidate.upper()
    if isinstance(candidate, str) and candidate not in {"", "transparent"}:
        try:
            red, green, blue = widget.winfo_rgb(candidate)
        except (AttributeError, tk.TclError):
            candidate = fallback
        else:
            return f"#{red // 256:02X}{green // 256:02X}{blue // 256:02X}"
    if fallback != color:
        return _coerce_hex(fallback, widget, "#000000")
    return "#000000"


def _geometry_position(x: int, y: int) -> str:
    return f"{x:+d}{y:+d}"


def blend_color(start: str, end: str, ratio: float) -> str:
    """Interpolate between two ``#RRGGBB`` colors."""

    if not isinstance(ratio, (int, float)) or isinstance(ratio, bool):
        raise TypeError("ratio должен быть числом")
    if not (
        isinstance(start, str)
        and isinstance(end, str)
        and len(start) == 7
        and len(end) == 7
        and start.startswith("#")
        and end.startswith("#")
    ):
        raise ValueError("Цвета должны иметь формат #RRGGBB")
    try:
        start_rgb = tuple(int(start[index : index + 2], 16) for index in (1, 3, 5))
        end_rgb = tuple(int(end[index : index + 2], 16) for index in (1, 3, 5))
    except ValueError as exc:
        raise ValueError("Цвета должны иметь формат #RRGGBB") from exc
    normalized = max(0.0, min(1.0, float(ratio)))
    mixed = tuple(
        round(left + (right - left) * normalized)
        for left, right in zip(start_rgb, end_rgb, strict=True)
    )
    return "#{:02X}{:02X}{:02X}".format(*mixed)


def _read_text(widget: Any) -> str:
    custom_reader = getattr(widget, "_animation_get_text", None)
    if callable(custom_reader):
        return str(custom_reader())
    try:
        value = widget.cget("text")
    except (AttributeError, tk.TclError):
        try:
            return str(widget.get("1.0", "end-1c"))
        except (AttributeError, tk.TclError):
            return ""
    return str(value)


def _set_text(widget: Any, text: str) -> None:
    custom_writer = getattr(widget, "_animation_set_text", None)
    if callable(custom_writer):
        custom_writer(text)
        return
    try:
        widget.configure(text=text)
    except (AttributeError, tk.TclError, ValueError):
        previous_state: str | None = None
    else:
        return

    try:
        previous_state = str(widget.cget("state"))
    except (AttributeError, tk.TclError, ValueError):
        previous_state = None
    try:
        if previous_state == "disabled":
            widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.see("1.0")
    except (AttributeError, tk.TclError) as exc:
        raise TypeError("Виджет не поддерживает изменение текста") from exc
    finally:
        if previous_state == "disabled":
            try:
                widget.configure(state="disabled")
            except (AttributeError, tk.TclError):
                previous_state = None


def _read_color(widget: Any, option: str) -> object:
    try:
        return widget.cget(option)
    except (AttributeError, tk.TclError, ValueError):
        return None


def _set_color(widget: Any, option: str, color: object) -> bool:
    try:
        widget.configure(**{option: color})
    except (AttributeError, tk.TclError, ValueError):
        return False
    return True


def _text_color_option(widget: Any) -> str:
    for option in ("text_color", "foreground", "fg"):
        value = _read_color(widget, option)
        if value is not None:
            return option
    return "text_color"


def _background_color(widget: Any) -> str:
    current: Any = widget
    for _ in range(4):
        current = getattr(current, "master", None)
        if current is None:
            break
        for option in ("fg_color", "background", "bg"):
            value = _read_color(current, option)
            if value is not None and value != "transparent":
                return _coerce_hex(value, widget, DARK_BG)
    return DARK_BG


@dataclass(slots=True)
class _TypewriterState:
    widget: Any
    text: str
    delay: int
    callback: AnimationCallback | None
    offset: int = 0
    blink_step: int = 0
    job: str | None = None


class TypewriterEffect:
    """Reveal widget text one character at a time with a block cursor."""

    def __init__(self, *, sound_enabled: bool = False) -> None:
        self.sound_enabled = bool(sound_enabled)
        self._states: dict[int, _TypewriterState] = {}

    def typewrite(
        self,
        widget: Any,
        text: str,
        delay: int = 30,
        callback: AnimationCallback | None = None,
    ) -> None:
        if not isinstance(text, str):
            raise TypeError("text должен быть строкой")
        if isinstance(delay, bool) or not isinstance(delay, int):
            raise TypeError("delay должен быть целым числом")
        if delay < 0 or delay > 5_000:
            raise ValueError("delay должен быть от 0 до 5000 мс")
        if callback is not None and not callable(callback):
            raise TypeError("callback должен быть вызываемым")

        self.stop(widget)
        state = _TypewriterState(
            widget=widget, text=text, delay=delay, callback=callback
        )
        self._states[id(widget)] = state
        if delay == 0:
            state.offset = len(text)
            _set_text(widget, f"{text}█")
            state.job = _after(widget, 0, lambda: self._blink_cursor(state))
            return
        _set_text(widget, "█")
        state.job = _after(widget, delay, lambda: self._step(state))

    def stop(self, widget: Any, *, finish: bool = False) -> None:
        state = self._states.pop(id(widget), None)
        if state is None:
            return
        _cancel_after(state.widget, state.job)
        if finish and _widget_exists(state.widget):
            _set_text(state.widget, state.text)

    def stop_all(self) -> None:
        for state in tuple(self._states.values()):
            self.stop(state.widget)

    def _step(self, state: _TypewriterState) -> None:
        state.job = None
        if self._states.get(id(state.widget)) is not state or not _widget_exists(
            state.widget
        ):
            self._states.pop(id(state.widget), None)
            return
        if state.offset < len(state.text):
            state.offset += 1
            _set_text(state.widget, f"{state.text[: state.offset]}█")
            self._keyboard_click()
            state.job = _after(
                state.widget,
                state.delay,
                lambda: self._step(state),
            )
            return
        self._blink_cursor(state)

    def _blink_cursor(self, state: _TypewriterState) -> None:
        if self._states.get(id(state.widget)) is not state or not _widget_exists(
            state.widget
        ):
            self._states.pop(id(state.widget), None)
            return
        blink_cycles = int(getattr(state.widget, "_typewriter_blink_steps", 4))
        if state.blink_step >= max(0, blink_cycles):
            _set_text(state.widget, state.text)
            self._states.pop(id(state.widget), None)
            if state.callback is not None:
                state.callback()
            return
        cursor = "" if state.blink_step % 2 == 0 else "█"
        _set_text(state.widget, f"{state.text}{cursor}")
        state.blink_step += 1
        state.job = _after(state.widget, 160, lambda: self._blink_cursor(state))

    def _keyboard_click(self) -> None:
        if not self.sound_enabled:
            return
        try:
            import winsound

            winsound.Beep(1_800, 4)
        except (ImportError, RuntimeError, OSError):
            self.sound_enabled = False


@dataclass(slots=True)
class _GlitchState:
    widget: Any
    original: str
    rounds: int
    duration: int
    current_round: int = 0
    job: str | None = None


class GlitchEffect:
    """Temporarily corrupt text with block symbols and restore it."""

    def __init__(self, *, random_source: random.Random | None = None) -> None:
        self._random = random_source or random.SystemRandom()
        self._states: dict[int, _GlitchState] = {}

    def glitch(self, widget: Any, duration: int = 500) -> None:
        if isinstance(duration, bool) or not isinstance(duration, int):
            raise TypeError("duration должен быть целым числом")
        if duration < 100 or duration > 10_000:
            raise ValueError("duration должен быть от 100 до 10000 мс")
        self.stop(widget)
        state = _GlitchState(
            widget=widget,
            original=_read_text(widget),
            rounds=self._random.randint(2, 3),
            duration=duration,
        )
        self._states[id(widget)] = state
        self._show_corruption(state)

    def stop(self, widget: Any) -> None:
        state = self._states.pop(id(widget), None)
        if state is None:
            return
        _cancel_after(state.widget, state.job)
        if _widget_exists(state.widget):
            _set_text(state.widget, state.original)

    def stop_all(self) -> None:
        for state in tuple(self._states.values()):
            self.stop(state.widget)

    def _show_corruption(self, state: _GlitchState) -> None:
        if self._states.get(id(state.widget)) is not state or not _widget_exists(
            state.widget
        ):
            return
        corrupted = "".join(
            self._random.choice(_GLITCH_SYMBOLS)
            if not char.isspace() and self._random.random() < 0.45
            else char
            for char in state.original
        )
        _set_text(state.widget, corrupted)
        visible_ms = min(65, max(35, state.duration // (state.rounds * 3)))
        state.job = _after(
            state.widget,
            visible_ms,
            lambda: self._restore_round(state),
        )

    def _restore_round(self, state: _GlitchState) -> None:
        state.job = None
        if self._states.get(id(state.widget)) is not state or not _widget_exists(
            state.widget
        ):
            return
        _set_text(state.widget, state.original)
        state.current_round += 1
        if state.current_round >= state.rounds:
            self._states.pop(id(state.widget), None)
            return
        state.job = _after(state.widget, 100, lambda: self._show_corruption(state))


@dataclass(slots=True)
class _FadeState:
    widget: Any
    option: str
    background: str
    target: str
    steps: int
    step: int = 0
    job: str | None = None


class FadeInEffect:
    """Fade text from its surrounding background color to its target color."""

    def __init__(self) -> None:
        self._states: dict[int, _FadeState] = {}

    def fade_in(self, widget: Any, duration: int = 800) -> None:
        if isinstance(duration, bool) or not isinstance(duration, int):
            raise TypeError("duration должен быть целым числом")
        if duration < 30 or duration > 30_000:
            raise ValueError("duration должен быть от 30 до 30000 мс")
        self.stop(widget)
        option = _text_color_option(widget)
        current = _read_color(widget, option)
        state = _FadeState(
            widget=widget,
            option=option,
            background=_background_color(widget),
            target=_coerce_hex(current, widget, TEXT_PRIMARY),
            steps=max(2, duration // 32),
        )
        self._states[id(widget)] = state
        _set_color(widget, option, state.background)
        state.job = _after(widget, 0, lambda: self._step(state, duration))

    def stop(self, widget: Any) -> None:
        state = self._states.pop(id(widget), None)
        if state is None:
            return
        _cancel_after(state.widget, state.job)
        if _widget_exists(state.widget):
            _set_color(state.widget, state.option, state.target)

    def stop_all(self) -> None:
        for state in tuple(self._states.values()):
            self.stop(state.widget)

    def _step(self, state: _FadeState, duration: int) -> None:
        state.job = None
        if self._states.get(id(state.widget)) is not state or not _widget_exists(
            state.widget
        ):
            self._states.pop(id(state.widget), None)
            return
        state.step += 1
        ratio = min(1.0, state.step / state.steps)
        _set_color(
            state.widget,
            state.option,
            blend_color(state.background, state.target, ratio),
        )
        if ratio >= 1.0:
            self._states.pop(id(state.widget), None)
            return
        interval = max(1, duration // state.steps)
        state.job = _after(state.widget, interval, lambda: self._step(state, duration))


@dataclass(slots=True)
class _PulseState:
    widget: Any
    option: str
    original: object
    color1: str
    color2: str
    speed: int
    phase: int = 0
    job: str | None = None


class PulseEffect:
    """Continuously pulse a button, frame, or progress bar until stopped."""

    _STEPS: Final[int] = 24

    def __init__(self) -> None:
        self._states: dict[int, _PulseState] = {}

    def pulse(
        self,
        widget: Any,
        color1: str,
        color2: str,
        speed: int = 500,
    ) -> None:
        if isinstance(speed, bool) or not isinstance(speed, int):
            raise TypeError("speed должен быть целым числом")
        if speed < 80 or speed > 30_000:
            raise ValueError("speed должен быть от 80 до 30000 мс")
        normalized1 = _coerce_hex(color1, widget, NEON_GREEN)
        normalized2 = _coerce_hex(color2, widget, DARK_BG)
        existing = self._states.get(id(widget))
        if (
            existing is not None
            and existing.color1 == normalized1
            and existing.color2 == normalized2
            and existing.speed == speed
        ):
            return
        self.stop(widget)
        option = self._choose_option(widget)
        state = _PulseState(
            widget=widget,
            option=option,
            original=_read_color(widget, option),
            color1=normalized1,
            color2=normalized2,
            speed=speed,
        )
        self._states[id(widget)] = state
        self._step(state)

    def stop(self, widget: Any, *, restore: bool = True) -> None:
        state = self._states.pop(id(widget), None)
        if state is None:
            return
        _cancel_after(state.widget, state.job)
        if restore and state.original is not None and _widget_exists(state.widget):
            _set_color(state.widget, state.option, state.original)

    def stop_all(self) -> None:
        for state in tuple(self._states.values()):
            self.stop(state.widget)

    @staticmethod
    def _choose_option(widget: Any) -> str:
        class_name = type(widget).__name__.lower()
        if (
            "progressbar" in class_name
            and _read_color(widget, "progress_color") is not None
        ):
            return "progress_color"
        if "button" in class_name and _read_color(widget, "fg_color") is not None:
            return "fg_color"
        for option in ("border_color", "fg_color", "progress_color"):
            if _read_color(widget, option) is not None:
                return option
        return "fg_color"

    def _step(self, state: _PulseState) -> None:
        state.job = None
        if self._states.get(id(state.widget)) is not state or not _widget_exists(
            state.widget
        ):
            self._states.pop(id(state.widget), None)
            return
        angle = (state.phase / self._STEPS) * math.tau
        ratio = (1.0 - math.cos(angle)) / 2.0
        _set_color(
            state.widget,
            state.option,
            blend_color(state.color1, state.color2, ratio),
        )
        state.phase = (state.phase + 1) % self._STEPS
        interval = max(12, state.speed // self._STEPS)
        state.job = _after(state.widget, interval, lambda: self._step(state))


@dataclass(slots=True)
class _MatrixColumn:
    x: int
    y: float
    speed: float
    length: int
    symbols: list[str]


class MatrixRain(tk.Canvas):
    """Canvas background with independently moving green character columns."""

    def __init__(
        self,
        master: Any,
        *,
        background: str = DARK_BG,
        column_width: int = 24,
        font_size: int = 11,
        random_source: random.Random | None = None,
        **kwargs: Any,
    ) -> None:
        if column_width < 10 or column_width > 100:
            raise ValueError("column_width должен быть от 10 до 100")
        if font_size < 7 or font_size > 40:
            raise ValueError("font_size должен быть от 7 до 40")
        kwargs.setdefault("bg", background)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        super().__init__(master, **kwargs)
        self._column_width = column_width
        self._font_size = font_size
        self._random = random_source or random.SystemRandom()
        self._columns: list[_MatrixColumn] = []
        self._job: str | None = None
        self._running = False
        self._destroyed = False
        self.bind("<Configure>", self._on_resize, add="+")

    def start(self) -> None:
        if self._destroyed or self._running:
            return
        self._running = True
        self._rebuild_columns()
        self._job = self.after(0, self._animate)

    def stop(self) -> None:
        self._running = False
        if self._job is not None:
            _cancel_after(self, self._job)
            self._job = None

    def _on_resize(self, _event: tk.Event[tk.Misc]) -> None:
        if self._running:
            self._rebuild_columns()

    def _rebuild_columns(self) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self._columns = [
            _MatrixColumn(
                x=x,
                y=float(self._random.randint(-height, height)),
                speed=self._random.uniform(2.0, 6.5),
                length=self._random.randint(5, 17),
                symbols=[
                    self._random.choice(("0", "1", "λ", "#", "@")) for _ in range(17)
                ],
            )
            for x in range(self._column_width // 2, width, self._column_width)
        ]

    def _animate(self) -> None:
        self._job = None
        if not self._running or self._destroyed:
            return
        height = max(1, self.winfo_height())
        self.delete("matrix-rain")
        spacing = self._font_size + 8
        for column in self._columns:
            if self._random.random() < 0.18:
                symbol_index = self._random.randrange(len(column.symbols))
                column.symbols[symbol_index] = self._random.choice(("0", "1", "#", "@"))
            for tail in range(column.length):
                y = column.y - tail * spacing
                if -spacing <= y <= height + spacing:
                    brightness = max(22, 210 - tail * 13)
                    blue = max(22, brightness // 3)
                    color = "#B8FFD0" if tail == 0 else f"#00{brightness:02X}{blue:02X}"
                    self.create_text(
                        column.x,
                        y,
                        text=column.symbols[tail],
                        fill=color,
                        font=(FONT_MONO_FAMILY, self._font_size),
                        tags="matrix-rain",
                    )
            column.y += column.speed
            if column.y - column.length * spacing > height:
                column.y = float(self._random.randint(-500, -20))
                column.speed = self._random.uniform(2.0, 6.5)
                column.length = self._random.randint(5, 17)
        self._job = self.after(65, self._animate)

    def destroy(self) -> None:
        self._destroyed = True
        self.stop()
        super().destroy()


class ProgressBarHack(ctk.CTkFrame):
    """Animated hacker progress indicator with a configurable final outcome."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        kwargs.setdefault("fg_color", "#08100C")
        kwargs.setdefault("corner_radius", 6)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_COLOR)
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.label = ctk.CTkLabel(
            self,
            text="Ожидание payload... 0%",
            text_color=NEON_GREEN,
            font=(FONT_MONO_FAMILY, 10, "bold"),
            anchor="w",
        )
        self.label.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        self.progress = ctk.CTkProgressBar(
            self,
            height=8,
            fg_color=DARK_BG,
            progress_color=NEON_GREEN,
            border_width=1,
            border_color="#17442A",
        )
        self.progress.grid(row=1, column=0, padx=10, pady=(1, 7), sticky="ew")
        self.progress.set(0.0)
        self._success = True
        self._job: str | None = None
        self._callback: AnimationCallback | None = None
        self._step_index = 0
        self._steps = 1
        self._duration = 3_000
        self._random = random.SystemRandom()
        self._destroyed = False

    def set_outcome(self, success: bool) -> None:
        if not isinstance(success, bool):
            raise TypeError("success должен быть bool")
        self._success = success

    def run_hack_progress(
        self,
        on_complete_callback: AnimationCallback,
        duration: int = 3_000,
    ) -> None:
        if not callable(on_complete_callback):
            raise TypeError("on_complete_callback должен быть вызываемым")
        if isinstance(duration, bool) or not isinstance(duration, int):
            raise TypeError("duration должен быть целым числом")
        if duration < 250 or duration > 120_000:
            raise ValueError("duration должен быть от 250 до 120000 мс")
        self.stop()
        self._callback = on_complete_callback
        self._duration = duration
        self._steps = max(20, duration // 55)
        self._step_index = 0
        color = NEON_GREEN if self._success else WARNING_RED
        self.configure(border_color=color)
        self.label.configure(text_color=color, text="Инициализация breach... 0%")
        self.progress.configure(progress_color=color, border_color=color)
        self.progress.set(0.0)
        self._job = self.after(0, self._advance)

    def stop(self) -> None:
        if self._job is not None:
            _cancel_after(self, self._job)
            self._job = None
        self._callback = None

    def _advance(self) -> None:
        self._job = None
        if self._destroyed:
            return
        self._step_index += 1
        ratio = min(1.0, self._step_index / self._steps)
        eased_ratio = 1.0 - (1.0 - ratio) ** 2
        percent = min(99, round(eased_ratio * 100))
        self.progress.set(eased_ratio)
        phrase_index = min(len(_HACK_PHRASES) - 1, int(ratio * len(_HACK_PHRASES)))
        phrase = _HACK_PHRASES[phrase_index]
        if self._random.random() < 0.08:
            phrase = self._random.choice(_HACK_PHRASES)
        self.label.configure(text=f"{phrase} {percent}%")
        if ratio < 1.0:
            interval = max(12, self._duration // self._steps)
            self._job = self.after(interval, self._advance)
            return

        final_text = "ДОСТУП ПОЛУЧЕН ✓" if self._success else "ОТКАЗАНО ✗"
        final_color = NEON_GREEN if self._success else WARNING_RED
        self.progress.set(1.0)
        self.progress.configure(progress_color=final_color)
        self.label.configure(text=final_text, text_color=final_color)
        self._job = self.after(280, self._complete)

    def _complete(self) -> None:
        self._job = None
        callback = self._callback
        self._callback = None
        if callback is not None and not self._destroyed:
            callback()

    def destroy(self) -> None:
        self._destroyed = True
        self.stop()
        super().destroy()


@dataclass(slots=True)
class _ShakeState:
    window: Any
    origin_x: int
    origin_y: int
    offsets: tuple[int, ...]
    interval: int
    index: int = 0
    job: str | None = None


class ScreenShake:
    """Short non-blocking horizontal shake for critical events."""

    _states: dict[int, _ShakeState] = {}

    @classmethod
    def shake(cls, window: Any, intensity: int = 5, duration: int = 500) -> None:
        if isinstance(intensity, bool) or not isinstance(intensity, int):
            raise TypeError("intensity должен быть целым числом")
        if isinstance(duration, bool) or not isinstance(duration, int):
            raise TypeError("duration должен быть целым числом")
        if intensity < 1 or intensity > 30:
            raise ValueError("intensity должен быть от 1 до 30")
        if duration < 80 or duration > 10_000:
            raise ValueError("duration должен быть от 80 до 10000 мс")
        cls.stop(window)
        try:
            origin_x = int(window.winfo_x())
            origin_y = int(window.winfo_y())
        except (AttributeError, tk.TclError, ValueError):
            return
        steps = max(4, duration // 34)
        offsets = tuple(
            round((intensity * (1.0 - index / steps)) * (-1 if index % 2 else 1))
            for index in range(steps)
        )
        state = _ShakeState(
            window=window,
            origin_x=origin_x,
            origin_y=origin_y,
            offsets=offsets,
            interval=max(12, duration // steps),
        )
        cls._states[id(window)] = state
        cls._step(state)

    @classmethod
    def stop(cls, window: Any) -> None:
        state = cls._states.pop(id(window), None)
        if state is None:
            return
        _cancel_after(state.window, state.job)
        if _widget_exists(state.window):
            try:
                state.window.geometry(
                    _geometry_position(state.origin_x, state.origin_y)
                )
            except (AttributeError, tk.TclError):
                return

    @classmethod
    def _step(cls, state: _ShakeState) -> None:
        state.job = None
        if cls._states.get(id(state.window)) is not state or not _widget_exists(
            state.window
        ):
            cls._states.pop(id(state.window), None)
            return
        if state.index >= len(state.offsets):
            cls._states.pop(id(state.window), None)
            try:
                state.window.geometry(
                    _geometry_position(state.origin_x, state.origin_y)
                )
            except (AttributeError, tk.TclError):
                return
            return
        offset = state.offsets[state.index]
        try:
            state.window.geometry(
                _geometry_position(state.origin_x + offset, state.origin_y)
            )
        except (AttributeError, tk.TclError):
            cls._states.pop(id(state.window), None)
            return
        state.index += 1
        state.job = _after(state.window, state.interval, lambda: cls._step(state))


@dataclass(slots=True)
class _NotificationState:
    window: Any
    target_x: int
    target_y: int
    start_x: int
    jobs: list[str]


class NotificationPopup:
    """Slide-in top-right notification manager with automatic fade-out."""

    WIDTH: Final[int] = 370
    HEIGHT: Final[int] = 92

    def __init__(self, master: Any) -> None:
        self.master = master
        self._states: list[_NotificationState] = []

    def show(self, message: str, type: str = "success") -> None:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message должен быть непустой строкой")
        if not isinstance(type, str) or type not in _NOTIFICATION_STYLES:
            allowed = ", ".join(_NOTIFICATION_STYLES)
            raise ValueError(f"type должен быть одним из: {allowed}")
        color, icon = _NOTIFICATION_STYLES[type]
        window = ctk.CTkToplevel(self.master)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(fg_color=DARK_BG)

        card = ctk.CTkFrame(
            window,
            fg_color="#101820",
            corner_radius=10,
            border_width=2,
            border_color=color,
        )
        card.pack(fill="both", expand=True, padx=2, pady=2)
        ctk.CTkLabel(
            card,
            text=icon,
            width=44,
            text_color=color,
            font=(FONT_MONO_FAMILY, 25, "bold"),
        ).grid(row=0, column=0, padx=(10, 4), pady=14, sticky="ns")
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            card,
            text=message,
            text_color=TEXT_PRIMARY,
            font=("Inter", 12, "bold"),
            wraplength=280,
            justify="left",
            anchor="w",
        ).grid(row=0, column=1, padx=(2, 14), pady=14, sticky="nsew")

        root_x = int(self.master.winfo_rootx())
        root_y = int(self.master.winfo_rooty())
        root_width = max(self.WIDTH + 20, int(self.master.winfo_width()))
        target_x = root_x + root_width - self.WIDTH - 18
        target_y = root_y + 18 + len(self._states) * (self.HEIGHT + 8)
        start_x = root_x + root_width + 12
        position = _geometry_position(start_x, target_y)
        window.geometry(f"{self.WIDTH}x{self.HEIGHT}{position}")
        try:
            window.attributes("-alpha", 0.96)
        except tk.TclError:
            window.configure(fg_color=DARK_BG)
        window.deiconify()
        window.lift()

        state = _NotificationState(
            window=window,
            target_x=target_x,
            target_y=target_y,
            start_x=start_x,
            jobs=[],
        )
        self._states.append(state)
        self._slide(state, 0)
        state.jobs.append(window.after(3_000, lambda: self._fade_out(state, 0)))
        window.bind("<Button-1>", lambda _event: self._close(state), add="+")

    def close_all(self) -> None:
        for state in tuple(self._states):
            self._close(state)

    def _slide(self, state: _NotificationState, step: int) -> None:
        if state not in self._states or not _widget_exists(state.window):
            return
        steps = 14
        ratio = min(1.0, step / steps)
        eased = 1.0 - (1.0 - ratio) ** 3
        x = round(state.start_x + (state.target_x - state.start_x) * eased)
        state.window.geometry(_geometry_position(x, state.target_y))
        if step < steps:
            state.jobs.append(
                state.window.after(16, lambda: self._slide(state, step + 1))
            )

    def _fade_out(self, state: _NotificationState, step: int) -> None:
        if state not in self._states or not _widget_exists(state.window):
            return
        steps = 16
        ratio = min(1.0, step / steps)
        try:
            state.window.attributes("-alpha", max(0.0, 0.96 * (1.0 - ratio)))
        except tk.TclError:
            x = state.target_x + round(ratio * (self.WIDTH + 20))
            state.window.geometry(_geometry_position(x, state.target_y))
        if step >= steps:
            self._close(state)
            return
        state.jobs.append(
            state.window.after(28, lambda: self._fade_out(state, step + 1))
        )

    def _close(self, state: _NotificationState) -> None:
        if state not in self._states:
            return
        self._states.remove(state)
        for job in state.jobs:
            _cancel_after(state.window, job)
        if _widget_exists(state.window):
            try:
                state.window.destroy()
            except tk.TclError:
                state.jobs.clear()
        self._reposition()

    def _reposition(self) -> None:
        root_y = int(self.master.winfo_rooty())
        for index, state in enumerate(self._states):
            state.target_y = root_y + 18 + index * (self.HEIGHT + 8)
            if _widget_exists(state.window):
                state.window.geometry(
                    _geometry_position(state.target_x, state.target_y)
                )


__all__ = [
    "AnimationCallback",
    "FadeInEffect",
    "GlitchEffect",
    "MatrixRain",
    "NotificationPopup",
    "ProgressBarHack",
    "PulseEffect",
    "ScreenShake",
    "TypewriterEffect",
    "blend_color",
]
