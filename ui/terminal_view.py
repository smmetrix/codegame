"""Стилизованный интерактивный терминал Cyberdeck OS."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final

import customtkinter as ctk

from config import (
    ACCENT_CYAN,
    BORDER_COLOR,
    DARK_BG,
    DARK_GRAY,
    FONT_MONO_FAMILY,
    MAX_TERMINAL_LINES,
    NEON_GREEN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WARNING_RED,
)


class TerminalLevel(str, Enum):
    OUTPUT = "output"
    SYSTEM = "system"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    COMMAND = "command"
    DEBUG = "debug"


TERMINAL_COLORS: Final[dict[TerminalLevel, str]] = {
    TerminalLevel.OUTPUT: NEON_GREEN,
    TerminalLevel.SYSTEM: ACCENT_CYAN,
    TerminalLevel.INFO: TEXT_PRIMARY,
    TerminalLevel.SUCCESS: "#5CFF95",
    TerminalLevel.WARNING: "#FFD166",
    TerminalLevel.ERROR: WARNING_RED,
    TerminalLevel.COMMAND: "#80CBC4",
    TerminalLevel.DEBUG: TEXT_MUTED,
}

TERMINAL_PREFIXES: Final[dict[TerminalLevel, str]] = {
    TerminalLevel.OUTPUT: "OUT",
    TerminalLevel.SYSTEM: "SYS",
    TerminalLevel.INFO: "INFO",
    TerminalLevel.SUCCESS: "OK",
    TerminalLevel.WARNING: "WARN",
    TerminalLevel.ERROR: "ERR",
    TerminalLevel.COMMAND: "CMD",
    TerminalLevel.DEBUG: "DBG",
}

CommandHandler = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class _TerminalMessage:
    text: str
    level: TerminalLevel
    animated: bool
    delay_ms: int


class TerminalView(ctk.CTkFrame):
    """Консоль с цветными каналами, command history и typewriter effect.

    Методы ``write`` и ``post`` безопасно принимают сообщения из фонового
    потока. Все обращения к Tk автоматически переносятся в главный UI-поток.
    """

    def __init__(
        self,
        master: Any,
        *,
        command_handler: CommandHandler | None = None,
        prompt: str = "ghost@deck:~$",
        typing_delay_ms: int = 9,
        max_lines: int = MAX_TERMINAL_LINES,
        show_timestamps: bool = False,
        font_size: int = 13,
        **kwargs: Any,
    ) -> None:
        if typing_delay_ms < 0 or typing_delay_ms > 1_000:
            raise ValueError("typing_delay_ms должен быть от 0 до 1000")
        if max_lines < 100:
            raise ValueError("max_lines не может быть меньше 100")
        if font_size < 8 or font_size > 40:
            raise ValueError("font_size должен быть от 8 до 40")

        kwargs.setdefault("fg_color", DARK_GRAY)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_COLOR)
        super().__init__(master, **kwargs)

        self._command_handler = command_handler
        self._prompt = prompt
        self._typing_delay_ms = typing_delay_ms
        self._max_lines = max_lines
        self._show_timestamps = show_timestamps
        self._ui_thread_id = threading.get_ident()
        self._incoming: queue.SimpleQueue[_TerminalMessage] = queue.SimpleQueue()
        self._messages: deque[_TerminalMessage] = deque()
        self._active_message: _TerminalMessage | None = None
        self._active_offset = 0
        self._animation_job: str | None = None
        self._incoming_job: str | None = None
        self._destroyed = False
        self._history: list[str] = []
        self._history_index = 0

        self._font = tkfont.Font(
            master=self,
            family=FONT_MONO_FAMILY,
            size=font_size,
        )

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_output()
        self._build_command_line()
        self._configure_tags()
        self._schedule_incoming_poll()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent", height=34)
        header.grid(row=0, column=0, padx=10, pady=(7, 2), sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        self.connection_dot = ctk.CTkLabel(
            header,
            text="●",
            width=18,
            text_color=NEON_GREEN,
            font=("Arial", 13),
        )
        self.connection_dot.grid(row=0, column=0, sticky="w")

        self.title_label = ctk.CTkLabel(
            header,
            text="CYBERDECK TERMINAL // LOCAL SANDBOX",
            text_color=NEON_GREEN,
            font=("Inter", 12, "bold"),
            anchor="w",
        )
        self.title_label.grid(row=0, column=1, sticky="w")

        self.queue_label = ctk.CTkLabel(
            header,
            text="IDLE",
            text_color=TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 10),
        )
        self.queue_label.grid(row=0, column=2, padx=8, sticky="e")

        ctk.CTkButton(
            header,
            text="CLEAR",
            width=58,
            height=24,
            fg_color="transparent",
            hover_color="#2B1820",
            border_width=1,
            border_color=BORDER_COLOR,
            text_color=TEXT_MUTED,
            font=("Inter", 10),
            command=self.clear,
        ).grid(row=0, column=3, sticky="e")

    def _build_output(self) -> None:
        output_frame = ctk.CTkFrame(
            self,
            fg_color="#05080B",
            corner_radius=4,
            border_width=1,
            border_color="#1F2A34",
        )
        output_frame.grid(row=1, column=0, padx=10, pady=3, sticky="nsew")
        output_frame.grid_columnconfigure(0, weight=1)
        output_frame.grid_rowconfigure(0, weight=1)

        self.output = tk.Text(
            output_frame,
            wrap="word",
            state="disabled",
            font=self._font,
            bg="#05080B",
            fg=NEON_GREEN,
            insertbackground=NEON_GREEN,
            selectbackground="#16445A",
            selectforeground=TEXT_PRIMARY,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            spacing1=1,
            spacing3=2,
            takefocus=True,
        )
        self.output.grid(row=0, column=0, sticky="nsew")

        self.scrollbar = ctk.CTkScrollbar(
            output_frame,
            orientation="vertical",
            width=14,
            command=self.output.yview,
            button_color=BORDER_COLOR,
            button_hover_color=ACCENT_CYAN,
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=self._on_output_yview)
        self.output.bind("<Control-l>", self._clear_shortcut)
        self.output.bind("<Command-l>", self._clear_shortcut)

    def _build_command_line(self) -> None:
        command_frame = ctk.CTkFrame(self, fg_color="transparent", height=38)
        command_frame.grid(row=2, column=0, padx=10, pady=(3, 8), sticky="ew")
        command_frame.grid_columnconfigure(1, weight=1)

        self.prompt_label = ctk.CTkLabel(
            command_frame,
            text=self._prompt,
            text_color=ACCENT_CYAN,
            font=(FONT_MONO_FAMILY, 12, "bold"),
            anchor="e",
        )
        self.prompt_label.grid(row=0, column=0, padx=(2, 8), sticky="e")

        self.command_entry = ctk.CTkEntry(
            command_frame,
            height=30,
            border_width=1,
            border_color=BORDER_COLOR,
            fg_color=DARK_BG,
            text_color=TEXT_PRIMARY,
            placeholder_text="help",
            placeholder_text_color="#55606D",
            font=(FONT_MONO_FAMILY, 12),
        )
        self.command_entry.grid(row=0, column=1, sticky="ew")
        self.command_entry.bind("<Return>", self._submit_command)
        self.command_entry.bind("<Up>", self._history_previous)
        self.command_entry.bind("<Down>", self._history_next)
        self.command_entry.bind("<Control-l>", self._clear_shortcut)
        self.command_entry.bind("<Command-l>", self._clear_shortcut)

    def _on_output_yview(self, first: str, last: str) -> None:
        self.scrollbar.set(float(first), float(last))

    def _configure_tags(self) -> None:
        for level, color in TERMINAL_COLORS.items():
            self.output.tag_configure(level.value, foreground=color)
        self.output.tag_configure(
            "timestamp", foreground="#4D5966", font=(FONT_MONO_FAMILY, 10)
        )
        self.output.tag_configure(
            "prefix", foreground=ACCENT_CYAN, font=(FONT_MONO_FAMILY, 11, "bold")
        )

    def write(
        self,
        text: object,
        level: TerminalLevel = TerminalLevel.OUTPUT,
        *,
        animate: bool = True,
        delay_ms: int | None = None,
    ) -> None:
        """Добавляет сообщение; вызов допустим из любого Python-потока."""

        if not isinstance(level, TerminalLevel):
            raise TypeError("level должен быть значением TerminalLevel")
        if self._destroyed:
            return
        rendered = str(text).replace("\r\n", "\n").replace("\r", "\n")
        actual_delay = self._typing_delay_ms if delay_ms is None else delay_ms
        if actual_delay < 0 or actual_delay > 1_000:
            raise ValueError("delay_ms должен быть от 0 до 1000")
        message = _TerminalMessage(
            text=rendered,
            level=level,
            animated=animate and actual_delay > 0,
            delay_ms=actual_delay,
        )

        if threading.get_ident() != self._ui_thread_id:
            self._incoming.put(message)
            return
        self._enqueue_message(message)

    def post(
        self,
        text: object,
        level: TerminalLevel = TerminalLevel.OUTPUT,
        *,
        animate: bool = True,
        delay_ms: int | None = None,
    ) -> None:
        """Явный thread-safe alias для фоновых Sandbox workers."""

        self.write(text, level, animate=animate, delay_ms=delay_ms)

    def write_system(self, text: object, *, animate: bool = True) -> None:
        self.write(text, TerminalLevel.SYSTEM, animate=animate)

    def write_error(self, text: object, *, animate: bool = False) -> None:
        self.write(text, TerminalLevel.ERROR, animate=animate)

    def write_success(self, text: object, *, animate: bool = True) -> None:
        self.write(text, TerminalLevel.SUCCESS, animate=animate)

    def write_stdout(self, stdout: str, *, animate: bool = False) -> None:
        if not stdout:
            return
        for line in stdout.rstrip("\n").splitlines():
            self.write(line, TerminalLevel.OUTPUT, animate=animate)

    def write_stderr(self, stderr: str, *, animate: bool = False) -> None:
        if not stderr:
            return
        for line in stderr.rstrip("\n").splitlines():
            self.write(line, TerminalLevel.ERROR, animate=animate)

    def _enqueue_message(self, message: _TerminalMessage) -> None:
        if self._destroyed:
            return
        self._messages.append(message)
        self.queue_label.configure(text=f"QUEUE {len(self._messages)}")
        if self._active_message is None:
            self._start_next_message()

    def _start_next_message(self) -> None:
        if self._destroyed or self._active_message is not None:
            return
        if not self._messages:
            self.queue_label.configure(text="IDLE", text_color=TEXT_MUTED)
            return

        self._active_message = self._messages.popleft()
        self._active_offset = 0
        self.queue_label.configure(text="RX", text_color=NEON_GREEN)
        self._insert_message_header(self._active_message.level)

        if self._active_message.animated:
            self._schedule_animation(0)
        else:
            self._insert_output(
                self._ensure_newline(self._active_message.text),
                self._active_message.level.value,
            )
            self._finish_active_message()

    def _insert_message_header(self, level: TerminalLevel) -> None:
        self._set_output_state("normal")
        if self._show_timestamps:
            from datetime import datetime

            timestamp = datetime.now().strftime("%H:%M:%S")
            self.output.insert("end", f"[{timestamp}] ", "timestamp")
        prefix = TERMINAL_PREFIXES[level]
        self.output.insert("end", f"[{prefix}] ", "prefix")
        self._set_output_state("disabled")

    def _schedule_animation(self, delay: int) -> None:
        if self._destroyed:
            return
        self._animation_job = self.after(delay, self._type_next_chunk)

    def _type_next_chunk(self) -> None:
        self._animation_job = None
        message = self._active_message
        if self._destroyed or message is None:
            return

        rendered = self._ensure_newline(message.text)
        remaining = len(rendered) - self._active_offset
        if remaining <= 0:
            self._finish_active_message()
            return

        chunk_size = self._chunk_size(len(rendered))
        end_offset = min(len(rendered), self._active_offset + chunk_size)
        chunk = rendered[self._active_offset : end_offset]
        self._insert_output(chunk, message.level.value)
        self._active_offset = end_offset

        if self._active_offset >= len(rendered):
            self._finish_active_message()
        else:
            self._schedule_animation(message.delay_ms)

    @staticmethod
    def _chunk_size(message_length: int) -> int:
        if message_length <= 180:
            return 1
        if message_length <= 800:
            return 3
        return 8

    def _finish_active_message(self) -> None:
        self._active_message = None
        self._active_offset = 0
        self._trim_lines()
        self._start_next_message()

    def _insert_output(self, text: str, tag: str) -> None:
        self._set_output_state("normal")
        self.output.insert("end", text, tag)
        self.output.see("end")
        self._set_output_state("disabled")

    @staticmethod
    def _ensure_newline(text: str) -> str:
        return text if text.endswith("\n") else f"{text}\n"

    def _trim_lines(self) -> None:
        self._set_output_state("normal")
        try:
            line_count = int(self.output.index("end-1c").split(".")[0])
            excess = line_count - self._max_lines
            if excess > 0:
                self.output.delete("1.0", f"{excess + 1}.0")
        finally:
            self._set_output_state("disabled")

    def _set_output_state(self, state: str) -> None:
        self.output.configure(state=state)

    def _schedule_incoming_poll(self) -> None:
        if self._destroyed:
            return
        self._incoming_job = self.after(35, self._poll_incoming)

    def _poll_incoming(self) -> None:
        self._incoming_job = None
        if self._destroyed:
            return
        while True:
            try:
                message = self._incoming.get_nowait()
            except queue.Empty:
                break
            self._enqueue_message(message)
        self._schedule_incoming_poll()

    def _submit_command(self, _event: tk.Event[tk.Misc]) -> str:
        command = self.command_entry.get().strip()
        if not command:
            return "break"
        self.command_entry.delete(0, "end")
        if not self._history or self._history[-1] != command:
            self._history.append(command)
        self._history_index = len(self._history)
        self.write(
            f"{self._prompt} {command}",
            TerminalLevel.COMMAND,
            animate=False,
        )

        if self._command_handler is None:
            self.write_error("Командный обработчик не подключен.")
            return "break"
        try:
            response = self._command_handler(command)
        except Exception as exc:
            self.write_error(f"{type(exc).__name__}: {exc}")
        else:
            if response:
                self.write(response, TerminalLevel.INFO, animate=True)
        return "break"

    def _history_previous(self, _event: tk.Event[tk.Misc]) -> str:
        if not self._history:
            return "break"
        self._history_index = max(0, self._history_index - 1)
        self._replace_command(self._history[self._history_index])
        return "break"

    def _history_next(self, _event: tk.Event[tk.Misc]) -> str:
        if not self._history:
            return "break"
        self._history_index = min(len(self._history), self._history_index + 1)
        value = (
            ""
            if self._history_index == len(self._history)
            else self._history[self._history_index]
        )
        self._replace_command(value)
        return "break"

    def _replace_command(self, value: str) -> None:
        self.command_entry.delete(0, "end")
        self.command_entry.insert(0, value)
        self.command_entry.icursor("end")

    def _clear_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self.clear()
        return "break"

    def clear(self) -> None:
        """Очищает экран и отменяет ожидающую typewriter animation."""

        if self._animation_job is not None:
            self.after_cancel(self._animation_job)
            self._animation_job = None
        self._messages.clear()
        self._active_message = None
        self._active_offset = 0
        self._set_output_state("normal")
        self.output.delete("1.0", "end")
        self._set_output_state("disabled")
        self.queue_label.configure(text="IDLE", text_color=TEXT_MUTED)

    def flush_animation(self) -> None:
        """Мгновенно отображает активное сообщение и всю очередь."""

        if self._animation_job is not None:
            self.after_cancel(self._animation_job)
            self._animation_job = None
        if self._active_message is not None:
            rendered = self._ensure_newline(self._active_message.text)
            remainder = rendered[self._active_offset :]
            if remainder:
                self._insert_output(remainder, self._active_message.level.value)
            self._active_message = None
            self._active_offset = 0
        while self._messages:
            message = self._messages.popleft()
            self._insert_message_header(message.level)
            self._insert_output(self._ensure_newline(message.text), message.level.value)
        self._trim_lines()
        self.queue_label.configure(text="IDLE", text_color=TEXT_MUTED)

    def set_busy(self, busy: bool) -> None:
        """Показывает состояние Sandbox и блокирует command entry."""

        self.connection_dot.configure(text_color=WARNING_RED if busy else NEON_GREEN)
        self.title_label.configure(
            text=(
                "CYBERDECK TERMINAL // SANDBOX EXECUTING"
                if busy
                else "CYBERDECK TERMINAL // LOCAL SANDBOX"
            )
        )
        self.command_entry.configure(state="disabled" if busy else "normal")

    def set_command_handler(self, handler: CommandHandler | None) -> None:
        self._command_handler = handler

    def set_prompt(self, prompt: str) -> None:
        if not prompt.strip():
            raise ValueError("prompt не может быть пустым")
        self._prompt = prompt
        self.prompt_label.configure(text=prompt)

    def focus_command(self) -> None:
        self.command_entry.focus_set()

    def get_text(self) -> str:
        return self.output.get("1.0", "end-1c")

    def destroy(self) -> None:
        self._destroyed = True
        for job in (self._animation_job, self._incoming_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    continue
        self._messages.clear()
        while True:
            try:
                self._incoming.get_nowait()
            except queue.Empty:
                break
        super().destroy()


__all__ = [
    "CommandHandler",
    "TERMINAL_COLORS",
    "TERMINAL_PREFIXES",
    "TerminalLevel",
    "TerminalView",
]
