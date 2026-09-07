"""Масштабируемый редактор Python-кода для Cyberdeck OS."""

from __future__ import annotations

import builtins
import io
import keyword
import re
import tkinter as tk
import tkinter.font as tkfont
import tokenize
from collections.abc import Callable
from typing import Any, Final

import customtkinter as ctk

from config import (
    ACCENT_CYAN,
    BORDER_COLOR,
    DARK_BG,
    DARK_GRAY,
    FONT_MONO_FAMILY,
    NEON_GREEN,
    TAB_SIZE,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WARNING_RED,
)
from ui.animations import PulseEffect, blend_color


EditorCallback = Callable[[], None]
ChangeCallback = Callable[[str], None]

_EDITOR_BG: Final[str] = "#090D12"
_LINE_NUMBER_BG: Final[str] = "#0B1016"
_CURRENT_LINE_BG: Final[str] = "#111923"
_SELECTION_BG: Final[str] = "#16445A"

_SYNTAX_COLORS: Final[dict[str, str]] = {
    "keyword": "#FF7AB2",
    "builtin": ACCENT_CYAN,
    "string": "#A5D66A",
    "comment": "#6E7A88",
    "number": "#C6A0F6",
    "operator": "#89DDFF",
    "definition": "#FFD866",
    "decorator": "#FFCB6B",
    "error": WARNING_RED,
}

_BUILTIN_NAMES: Final[frozenset[str]] = frozenset(
    name for name in dir(builtins) if not name.startswith("_")
)


class CodeEditor(ctk.CTkFrame):
    """Редактор с line numbers, Python highlighting и горячими клавишами.

    Виджет не запускает пользовательский код сам. Контроллер игры передает
    callbacks ``on_run``, ``on_hint`` и ``on_reset``, поэтому UI остается
    отделен от Sandbox и бизнес-логики.
    """

    def __init__(
        self,
        master: Any,
        *,
        initial_code: str = "",
        on_run: EditorCallback | None = None,
        on_hint: EditorCallback | None = None,
        on_reset: EditorCallback | None = None,
        on_save: EditorCallback | None = None,
        on_change: ChangeCallback | None = None,
        font_size: int = 14,
        tab_size: int = TAB_SIZE,
        **kwargs: Any,
    ) -> None:
        if font_size < 8:
            raise ValueError("font_size не может быть меньше 8")
        if tab_size < 1 or tab_size > 16:
            raise ValueError("tab_size должен быть в диапазоне от 1 до 16")

        kwargs.setdefault("fg_color", DARK_GRAY)
        kwargs.setdefault("corner_radius", 8)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", BORDER_COLOR)
        super().__init__(master, **kwargs)

        self._on_run = on_run
        self._on_hint = on_hint
        self._on_reset = on_reset
        self._on_save = on_save
        self._on_change = on_change
        self._font_size = font_size
        self._tab_size = tab_size
        self._highlight_job: str | None = None
        self._line_number_job: str | None = None
        self._line_fade_jobs: list[str] = []
        self._line_fade_generation = 0
        self._known_line_count = 1
        self._run_pulse = PulseEffect()
        self._destroyed = False

        self._editor_font = tkfont.Font(
            master=self,
            family=FONT_MONO_FAMILY,
            size=self._font_size,
        )
        self._line_number_font = tkfont.Font(
            master=self,
            family=FONT_MONO_FAMILY,
            size=max(8, self._font_size - 2),
        )

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_text_area()
        self._build_statusbar()
        self._configure_tags()
        self._bind_shortcuts()
        self.set_code(initial_code, mark_clean=True)
        self.after_idle(self._refresh_visuals)

    def _build_toolbar(self) -> None:
        toolbar = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        toolbar.grid(row=0, column=0, padx=10, pady=(8, 5), sticky="ew")
        toolbar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            toolbar,
            text="</>  PYTHON EDITOR // mission.py",
            text_color=ACCENT_CYAN,
            font=("Inter", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        actions = ctk.CTkFrame(toolbar, fg_color="transparent")
        actions.grid(row=0, column=2, sticky="e")

        self.run_button = ctk.CTkButton(
            actions,
            text="> ЗАПУСТИТЬ  F5",
            width=146,
            height=30,
            fg_color=NEON_GREEN,
            hover_color="#00C853",
            text_color=DARK_BG,
            font=("Inter", 12, "bold"),
            command=self._invoke_run,
        )
        self.run_button.grid(row=0, column=0, padx=(0, 6))

        self.hint_button = ctk.CTkButton(
            actions,
            text="ПОДСКАЗКА",
            width=105,
            height=30,
            fg_color="transparent",
            hover_color="#12343B",
            border_width=1,
            border_color=ACCENT_CYAN,
            text_color=ACCENT_CYAN,
            command=self._invoke_hint,
        )
        self.hint_button.grid(row=0, column=1, padx=3)

        self.reset_button = ctk.CTkButton(
            actions,
            text="СБРОСИТЬ",
            width=92,
            height=30,
            fg_color="transparent",
            hover_color="#3A1721",
            border_width=1,
            border_color=WARNING_RED,
            text_color=WARNING_RED,
            command=self._invoke_reset,
        )
        self.reset_button.grid(row=0, column=2, padx=(3, 0))

    def _build_text_area(self) -> None:
        container = ctk.CTkFrame(
            self,
            fg_color=_EDITOR_BG,
            corner_radius=4,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        container.grid(row=1, column=0, padx=10, pady=3, sticky="nsew")
        container.grid_columnconfigure(1, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self.line_numbers = tk.Canvas(
            container,
            width=48,
            bg=_LINE_NUMBER_BG,
            highlightthickness=0,
            bd=0,
            takefocus=False,
        )
        self.line_numbers.grid(row=0, column=0, sticky="ns")

        self.text = tk.Text(
            container,
            wrap="none",
            undo=True,
            autoseparators=True,
            maxundo=-1,
            font=self._editor_font,
            bg=_EDITOR_BG,
            fg=TEXT_PRIMARY,
            insertbackground=NEON_GREEN,
            insertwidth=2,
            selectbackground=_SELECTION_BG,
            selectforeground=TEXT_PRIMARY,
            inactiveselectbackground="#17303B",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=8,
            spacing1=1,
            spacing3=1,
            tabs=(self._tab_pixel_width(),),
            takefocus=True,
        )
        self.text.grid(row=0, column=1, sticky="nsew")

        self.vertical_scrollbar = ctk.CTkScrollbar(
            container,
            orientation="vertical",
            width=14,
            command=self._on_vertical_scroll,
            button_color=BORDER_COLOR,
            button_hover_color=ACCENT_CYAN,
        )
        self.vertical_scrollbar.grid(row=0, column=2, sticky="ns")

        self.horizontal_scrollbar = ctk.CTkScrollbar(
            container,
            orientation="horizontal",
            height=14,
            command=self.text.xview,
            button_color=BORDER_COLOR,
            button_hover_color=ACCENT_CYAN,
        )
        self.horizontal_scrollbar.grid(row=1, column=1, columnspan=2, sticky="ew")

        self.text.configure(
            yscrollcommand=self._on_text_yview,
            xscrollcommand=self.horizontal_scrollbar.set,
        )
        self.line_numbers.bind("<Button-1>", self._select_line_from_gutter)
        self.text.bind("<<Modified>>", self._on_modified)
        self.text.bind("<Configure>", self._schedule_line_number_redraw)
        self.text.bind("<KeyRelease>", self._on_cursor_moved, add="+")
        self.text.bind("<ButtonRelease-1>", self._on_cursor_moved, add="+")
        self.text.bind("<MouseWheel>", self._schedule_line_number_redraw, add="+")
        self.text.bind("<Button-4>", self._schedule_line_number_redraw, add="+")
        self.text.bind("<Button-5>", self._schedule_line_number_redraw, add="+")

    def _build_statusbar(self) -> None:
        statusbar = ctk.CTkFrame(self, fg_color="transparent", height=24)
        statusbar.grid(row=2, column=0, padx=12, pady=(2, 6), sticky="ew")
        statusbar.grid_columnconfigure(0, weight=1)

        self.message_label = ctk.CTkLabel(
            statusbar,
            text="SANDBOXED PYTHON 3",
            text_color=TEXT_MUTED,
            font=("Inter", 10),
            anchor="w",
        )
        self.message_label.grid(row=0, column=0, sticky="w")

        self.cursor_label = ctk.CTkLabel(
            statusbar,
            text="Ln 1, Col 1",
            text_color=TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 10),
            anchor="e",
        )
        self.cursor_label.grid(row=0, column=1, sticky="e")

    def _configure_tags(self) -> None:
        self.text.tag_configure("current_line", background=_CURRENT_LINE_BG)
        self.text.tag_configure("syntax_keyword", foreground=_SYNTAX_COLORS["keyword"])
        self.text.tag_configure("syntax_builtin", foreground=_SYNTAX_COLORS["builtin"])
        self.text.tag_configure("syntax_string", foreground=_SYNTAX_COLORS["string"])
        self.text.tag_configure("syntax_comment", foreground=_SYNTAX_COLORS["comment"])
        self.text.tag_configure("syntax_number", foreground=_SYNTAX_COLORS["number"])
        self.text.tag_configure(
            "syntax_operator", foreground=_SYNTAX_COLORS["operator"]
        )
        self.text.tag_configure(
            "syntax_definition",
            foreground=_SYNTAX_COLORS["definition"],
            font=(FONT_MONO_FAMILY, self._font_size, "bold"),
        )
        self.text.tag_configure(
            "syntax_decorator", foreground=_SYNTAX_COLORS["decorator"]
        )
        self.text.tag_configure(
            "error_line",
            background="#35121C",
            foreground=WARNING_RED,
            underline=True,
        )
        self.text.tag_lower("current_line")

    def _bind_shortcuts(self) -> None:
        for sequence in ("<F5>", "<Control-Return>", "<Command-Return>"):
            self.text.bind(sequence, self._run_shortcut)
        for sequence in ("<Control-s>", "<Command-s>"):
            self.text.bind(sequence, self._save_shortcut)
        for sequence in ("<Control-slash>", "<Command-slash>"):
            self.text.bind(sequence, self._toggle_comment)
        self.text.bind("<Tab>", self._insert_tab)
        self.text.bind("<Shift-Tab>", self._dedent)
        self.text.bind("<ISO_Left_Tab>", self._dedent)
        self.text.bind("<Return>", self._insert_newline)
        self.text.bind("<Control-a>", self._select_all)
        self.text.bind("<Command-a>", self._select_all)

    def _tab_pixel_width(self) -> int:
        return self._editor_font.measure(" " * self._tab_size)

    def _on_modified(self, _event: tk.Event[tk.Misc]) -> None:
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        self.clear_error_line()
        self._schedule_highlight()
        self._schedule_line_number_redraw()
        self._update_cursor_label()
        if self._on_change is not None:
            self._on_change(self.get_code())

    def _on_cursor_moved(self, _event: tk.Event[tk.Misc]) -> None:
        self._highlight_current_line()
        self._update_cursor_label()
        self._schedule_line_number_redraw()

    def _on_text_yview(self, first: str, last: str) -> None:
        self.vertical_scrollbar.set(float(first), float(last))
        self._schedule_line_number_redraw()

    def _on_vertical_scroll(self, *args: str) -> None:
        self.text.yview(*args)
        self._schedule_line_number_redraw()

    def _schedule_highlight(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if self._destroyed:
            return
        if self._highlight_job is not None:
            self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(80, self._highlight_syntax)

    def _schedule_line_number_redraw(
        self, _event: tk.Event[tk.Misc] | None = None
    ) -> None:
        if self._destroyed or self._line_number_job is not None:
            return
        self._line_number_job = self.after_idle(self._draw_line_numbers)

    def _refresh_visuals(self) -> None:
        if self._destroyed:
            return
        self._highlight_syntax()
        self._highlight_current_line()
        self._draw_line_numbers()
        self._update_cursor_label()

    def _highlight_syntax(self) -> None:
        self._highlight_job = None
        if self._destroyed:
            return
        syntax_tags = (
            "syntax_keyword",
            "syntax_builtin",
            "syntax_string",
            "syntax_comment",
            "syntax_number",
            "syntax_operator",
            "syntax_definition",
            "syntax_decorator",
        )
        for tag in syntax_tags:
            self.text.tag_remove(tag, "1.0", "end")

        source = self.get_code()
        expect_definition_name = False
        decorator_line = -1
        try:
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)
            for token_info in tokens:
                token_type = token_info.type
                token_value = token_info.string
                start = f"{token_info.start[0]}.{token_info.start[1]}"
                end = f"{token_info.end[0]}.{token_info.end[1]}"
                tag: str | None = None

                if token_type == tokenize.NAME:
                    if expect_definition_name:
                        tag = "syntax_definition"
                        expect_definition_name = False
                    elif keyword.iskeyword(token_value):
                        tag = "syntax_keyword"
                        expect_definition_name = token_value in {"def", "class"}
                    elif token_value in _BUILTIN_NAMES:
                        tag = "syntax_builtin"
                    elif token_info.start[0] == decorator_line:
                        tag = "syntax_decorator"
                elif token_type == tokenize.STRING:
                    tag = "syntax_string"
                elif token_type == tokenize.COMMENT:
                    tag = "syntax_comment"
                elif token_type == tokenize.NUMBER:
                    tag = "syntax_number"
                elif token_type == tokenize.OP:
                    tag = "syntax_operator"
                    if token_value == "@":
                        decorator_line = token_info.start[0]
                elif token_type not in {
                    tokenize.ENCODING,
                    tokenize.INDENT,
                    tokenize.DEDENT,
                    tokenize.NEWLINE,
                    tokenize.NL,
                    tokenize.ENDMARKER,
                }:
                    expect_definition_name = False

                if tag is not None and token_info.start != token_info.end:
                    self.text.tag_add(tag, start, end)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            # Незавершенный код во время печати допустим; корректные токены уже окрашены.
            self.message_label.configure(
                text="КОД ЕЩЕ НЕ ЗАВЕРШЕН", text_color=WARNING_RED
            )
        else:
            self.message_label.configure(
                text="SANDBOXED PYTHON 3", text_color=TEXT_MUTED
            )

    def _draw_line_numbers(self) -> None:
        self._line_number_job = None
        if self._destroyed:
            return
        self._cancel_line_number_fade()
        self.line_numbers.delete("all")
        new_items: list[tuple[int, str]] = []
        try:
            index = self.text.index("@0,0")
            last_line = int(self.text.index("end-1c").split(".")[0])
            self._known_line_count = min(self._known_line_count, last_line)
            digits = max(2, len(str(last_line)))
            gutter_width = self._line_number_font.measure("9" * digits) + 20
            self.line_numbers.configure(width=gutter_width)

            while True:
                display_info = self.text.dlineinfo(index)
                if display_info is None:
                    break
                y_position = display_info[1]
                line_number = index.split(".")[0]
                numeric_line = int(line_number)
                current_line = self.text.index("insert").split(".")[0]
                target_color = NEON_GREEN if line_number == current_line else TEXT_MUTED
                is_new = numeric_line > self._known_line_count
                item_id = self.line_numbers.create_text(
                    gutter_width - 10,
                    y_position,
                    anchor="ne",
                    text=line_number,
                    fill=_LINE_NUMBER_BG if is_new else target_color,
                    font=self._line_number_font,
                )
                if is_new:
                    new_items.append((item_id, target_color))
                index = self.text.index(f"{index}+1line")
        except (tk.TclError, ValueError):
            return
        if new_items:
            self._line_fade_generation += 1
            generation = self._line_fade_generation
            self._animate_line_numbers(
                new_items,
                step=0,
                final_line_count=last_line,
                generation=generation,
            )
        else:
            self._known_line_count = last_line

    def _animate_line_numbers(
        self,
        items: list[tuple[int, str]],
        *,
        step: int,
        final_line_count: int,
        generation: int,
    ) -> None:
        if self._destroyed or generation != self._line_fade_generation:
            return
        total_steps = 10
        ratio = min(1.0, step / total_steps)
        try:
            for item_id, target_color in items:
                self.line_numbers.itemconfigure(
                    item_id,
                    fill=blend_color(_LINE_NUMBER_BG, target_color, ratio),
                )
        except tk.TclError:
            return
        if step >= total_steps:
            self._known_line_count = final_line_count
            self._line_fade_jobs.clear()
            return
        job = self.after(
            28,
            lambda: self._animate_line_numbers(
                items,
                step=step + 1,
                final_line_count=final_line_count,
                generation=generation,
            ),
        )
        self._line_fade_jobs.append(job)

    def _cancel_line_number_fade(self) -> None:
        self._line_fade_generation += 1
        for job in self._line_fade_jobs:
            try:
                self.after_cancel(job)
            except tk.TclError:
                continue
        self._line_fade_jobs.clear()

    def _highlight_current_line(self) -> None:
        self.text.tag_remove("current_line", "1.0", "end")
        line_start = self.text.index("insert linestart")
        line_end = self.text.index("insert lineend+1c")
        self.text.tag_add("current_line", line_start, line_end)
        self.text.tag_lower("current_line")

    def _update_cursor_label(self) -> None:
        line, column = self.text.index("insert").split(".")
        self.cursor_label.configure(text=f"Ln {line}, Col {int(column) + 1}")

    def _select_line_from_gutter(self, event: tk.Event[tk.Canvas]) -> str:
        line_index = self.text.index(f"@0,{event.y}").split(".")[0]
        self.text.tag_remove("sel", "1.0", "end")
        self.text.tag_add("sel", f"{line_index}.0", f"{line_index}.0 lineend+1c")
        self.text.mark_set("insert", f"{line_index}.0")
        self.text.focus_set()
        self._on_cursor_moved(event)
        return "break"

    def _insert_tab(self, _event: tk.Event[tk.Misc]) -> str:
        selection = self._selected_line_range()
        spaces = " " * self._tab_size
        if selection is None:
            self.text.insert("insert", spaces)
            return "break"
        first_line, last_line = selection
        for line_number in range(first_line, last_line + 1):
            self.text.insert(f"{line_number}.0", spaces)
        self.text.tag_add("sel", f"{first_line}.0", f"{last_line}.0 lineend")
        return "break"

    def _dedent(self, _event: tk.Event[tk.Misc]) -> str:
        selection = self._selected_line_range()
        if selection is None:
            line_number = int(self.text.index("insert").split(".")[0])
            first_line = last_line = line_number
        else:
            first_line, last_line = selection

        for line_number in range(first_line, last_line + 1):
            line_text = self.text.get(f"{line_number}.0", f"{line_number}.0 lineend")
            removable = min(len(line_text) - len(line_text.lstrip(" ")), self._tab_size)
            if removable:
                self.text.delete(f"{line_number}.0", f"{line_number}.{removable}")
        if selection is not None:
            self.text.tag_add("sel", f"{first_line}.0", f"{last_line}.0 lineend")
        return "break"

    def _insert_newline(self, _event: tk.Event[tk.Misc]) -> str:
        before_cursor = self.text.get("insert linestart", "insert")
        indentation_match = re.match(r"^[ \t]*", before_cursor)
        indentation = indentation_match.group(0) if indentation_match else ""
        if before_cursor.rstrip().endswith(":"):
            indentation += " " * self._tab_size
        self.text.insert("insert", f"\n{indentation}")
        return "break"

    def _toggle_comment(self, _event: tk.Event[tk.Misc]) -> str:
        selection = self._selected_line_range()
        if selection is None:
            line_number = int(self.text.index("insert").split(".")[0])
            first_line = last_line = line_number
        else:
            first_line, last_line = selection

        lines = [
            self.text.get(f"{line_number}.0", f"{line_number}.0 lineend")
            for line_number in range(first_line, last_line + 1)
        ]
        non_empty = [line for line in lines if line.strip()]
        should_uncomment = bool(non_empty) and all(
            line.lstrip().startswith("#") for line in non_empty
        )

        for line_number, line_text in zip(
            range(first_line, last_line + 1), lines, strict=True
        ):
            if not line_text.strip():
                continue
            indentation = len(line_text) - len(line_text.lstrip(" "))
            if should_uncomment:
                comment_index = line_text.find("#", indentation)
                if comment_index >= 0:
                    delete_end = (
                        comment_index + 2
                        if line_text[comment_index:].startswith("# ")
                        else comment_index + 1
                    )
                    self.text.delete(
                        f"{line_number}.{comment_index}",
                        f"{line_number}.{delete_end}",
                    )
            else:
                self.text.insert(f"{line_number}.{indentation}", "# ")

        if selection is not None:
            self.text.tag_add("sel", f"{first_line}.0", f"{last_line}.0 lineend")
        return "break"

    def _selected_line_range(self) -> tuple[int, int] | None:
        try:
            first = self.text.index("sel.first")
            last = self.text.index("sel.last")
        except tk.TclError:
            return None
        first_line = int(first.split(".")[0])
        last_line = int(last.split(".")[0])
        if last.endswith(".0") and last_line > first_line:
            last_line -= 1
        return first_line, last_line

    def _select_all(self, _event: tk.Event[tk.Misc]) -> str:
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.mark_set("insert", "1.0")
        self.text.see("insert")
        return "break"

    def _run_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        self._invoke_run()
        return "break"

    def _save_shortcut(self, _event: tk.Event[tk.Misc]) -> str:
        if self._on_save is not None:
            self._on_save()
        return "break"

    def _invoke_run(self) -> None:
        if self._on_run is not None:
            self._on_run()

    def _invoke_hint(self) -> None:
        if self._on_hint is not None:
            self._on_hint()

    def _invoke_reset(self) -> None:
        if self._on_reset is not None:
            self._on_reset()

    def get_code(self) -> str:
        """Возвращает код без служебного перевода строки Tk в конце."""

        return self.text.get("1.0", "end-1c")

    def set_code(self, code: str, *, mark_clean: bool = False) -> None:
        if not isinstance(code, str):
            raise TypeError("code должен быть строкой")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", code)
        self.text.mark_set("insert", "1.0")
        self.text.edit_modified(False)
        if mark_clean:
            self.text.edit_reset()
        self.clear_error_line()
        self._schedule_highlight()
        self._schedule_line_number_redraw()
        self._highlight_current_line()
        self._update_cursor_label()

    def clear(self) -> None:
        self.set_code("", mark_clean=True)

    def set_font_size(self, size: int) -> None:
        """Меняет масштаб кода и line numbers без пересоздания виджета."""

        if size < 8 or size > 40:
            raise ValueError("Размер шрифта должен быть от 8 до 40")
        self._font_size = size
        self._editor_font.configure(size=size)
        self._line_number_font.configure(size=max(8, size - 2))
        self.text.configure(tabs=(self._tab_pixel_width(),))
        self.text.tag_configure(
            "syntax_definition", font=(FONT_MONO_FAMILY, size, "bold")
        )
        self._schedule_line_number_redraw()

    def mark_error_line(self, line_number: int, message: str | None = None) -> None:
        """Подсвечивает строку ошибки Sandbox и прокручивает к ней редактор."""

        if isinstance(line_number, bool) or not isinstance(line_number, int):
            raise TypeError("line_number должен быть целым числом")
        total_lines = int(self.text.index("end-1c").split(".")[0])
        if not 1 <= line_number <= total_lines:
            raise ValueError(f"Строка {line_number} отсутствует в редакторе")
        self.clear_error_line()
        self.text.tag_add(
            "error_line", f"{line_number}.0", f"{line_number}.0 lineend+1c"
        )
        self.text.see(f"{line_number}.0")
        if message:
            self.message_label.configure(text=message, text_color=WARNING_RED)

    def clear_error_line(self) -> None:
        self.text.tag_remove("error_line", "1.0", "end")

    def set_running(self, running: bool) -> None:
        """Блокирует повторный запуск, не запрещая читать или исправлять код."""

        state = "disabled" if running else "normal"
        label = "ВЫПОЛНЕНИЕ..." if running else "> ЗАПУСТИТЬ  F5"
        self.run_button.configure(state=state, text=label)
        if running:
            self._run_pulse.pulse(
                self.run_button,
                NEON_GREEN,
                "#003311",
                speed=500,
            )
        else:
            self._run_pulse.stop(self.run_button)
        self.message_label.configure(
            text="SANDBOX EXECUTING" if running else "SANDBOXED PYTHON 3",
            text_color=WARNING_RED if running else TEXT_MUTED,
        )

    def focus_editor(self) -> None:
        self.text.focus_set()

    @property
    def text_widget(self) -> tk.Text:
        """Доступ к native Text для интеграции автодополнения и тестов."""

        return self.text

    def destroy(self) -> None:
        self._destroyed = True
        self._run_pulse.stop_all()
        self._cancel_line_number_fade()
        for job in (self._highlight_job, self._line_number_job):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    continue
        super().destroy()


__all__ = ["ChangeCallback", "CodeEditor", "EditorCallback"]
