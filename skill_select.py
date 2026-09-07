"""Полноэкранный выбор навыка при первом запуске GreyHat Cyberdeck."""

from __future__ import annotations

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
    TEXT_MUTED,
    TEXT_PRIMARY,
    WARNING_RED,
)
from game_state import SKILL_LEVELS
from ui.animations import MatrixRain


@dataclass(frozen=True, slots=True)
class SkillOption:
    id: str
    title: str
    icon: str
    description: str
    effect: str
    accent: str


SKILL_OPTIONS: Final[tuple[SkillOption, ...]] = (
    SkillOption(
        id="zero",
        title="Нулевой",
        icon="👶",
        description="Я никогда не писал код. Не знаю, что такое переменная.",
        effect=(
            "Все 15 миссий доступны. Максимально подробное обучение, автоматические "
            "подсказки, таймеры ×3 и комментарии на каждой строке."
        ),
        accent=NEON_GREEN,
    ),
    SkillOption(
        id="beginner",
        title="Новичок",
        icon="🌱",
        description="Знаю print() и переменные, но циклы — это сложно.",
        effect=(
            "Первые три миссии упрощены, таймеры ×2, бесплатные подсказки по запросу "
            "и базовые комментарии в коде."
        ),
        accent="#6DFF9A",
    ),
    SkillOption(
        id="practice",
        title="Практик",
        icon="💻",
        description="Умею писать циклы, функции, знаю списки и словари.",
        effect=(
            "Стандартная сложность, краткое обучение, обычные таймеры. "
            "Подсказка стоит 10 BTC."
        ),
        accent=ACCENT_CYAN,
    ),
    SkillOption(
        id="advanced",
        title="Продвинутый",
        icon="⚡",
        description="Пишу на Python уверенно, знаю ООП и библиотеки.",
        effect=(
            "Обучение скрыто, таймеры ×0.7, подсказка стоит 30 BTC, "
            "Trace Meter быстрее реагирует на ошибки."
        ),
        accent="#B48CFF",
    ),
    SkillOption(
        id="senior",
        title="Senior",
        icon="👑",
        description="Python — мой родной язык. Удиви меня.",
        effect=(
            "Минимальное время, подсказки отключены, Senior-ловушки и секретные "
            "условия. Очевидные решения O(n²) отклоняются."
        ),
        accent="#FFD166",
    ),
)


def _blend_color(start: str, end: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    start_rgb = tuple(int(start[index : index + 2], 16) for index in (1, 3, 5))
    end_rgb = tuple(int(end[index : index + 2], 16) for index in (1, 3, 5))
    mixed = tuple(
        round(left + (right - left) * ratio)
        for left, right in zip(start_rgb, end_rgb, strict=True)
    )
    return "#{:02X}{:02X}{:02X}".format(*mixed)


class SkillCard(ctk.CTkFrame):
    """Анимированная карточка одного уровня навыка."""

    def __init__(
        self,
        master: Any,
        option: SkillOption,
        on_select: Callable[[SkillOption], None],
        *,
        card_width: int,
        card_height: int,
    ) -> None:
        super().__init__(
            master,
            width=card_width,
            height=card_height,
            fg_color="#111820",
            corner_radius=12,
            border_width=2,
            border_color=BORDER_COLOR,
        )
        self.option = option
        self._on_select = on_select
        self._base_width = card_width
        self._base_height = card_height
        self._selected = False
        self._dimmed = False
        self._pulse_job: str | None = None
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.icon_label = ctk.CTkLabel(
            self,
            text=option.icon,
            font=("Segoe UI Emoji", 40),
            text_color=option.accent,
        )
        self.icon_label.grid(row=0, column=0, padx=15, pady=(22, 8))
        self.title_label = ctk.CTkLabel(
            self,
            text=option.title,
            font=("Inter", 18, "bold"),
            text_color=TEXT_PRIMARY,
        )
        self.title_label.grid(row=1, column=0, padx=15, pady=3)
        self.description_label = ctk.CTkLabel(
            self,
            text=option.description,
            font=("Inter", 12),
            text_color="#C5D0DB",
            wraplength=max(100, card_width - 40),
            justify="left",
            anchor="n",
        )
        self.description_label.grid(row=2, column=0, padx=18, pady=(10, 8), sticky="ew")
        self.effect_label = ctk.CTkLabel(
            self,
            text=option.effect,
            font=("Inter", 11),
            text_color=TEXT_MUTED,
            wraplength=max(100, card_width - 40),
            justify="left",
            anchor="n",
        )
        self.effect_label.grid(row=3, column=0, padx=18, pady=8, sticky="nsew")
        self.select_label = ctk.CTkLabel(
            self,
            text=f"[{option.id.upper()}]",
            font=(FONT_MONO_FAMILY, 10, "bold"),
            text_color=option.accent,
        )
        self.select_label.grid(row=4, column=0, padx=15, pady=(8, 18))

        self._bind_pointer(self)

    def _bind_pointer(self, widget: Any) -> None:
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Button-1>", self._on_click, add="+")
        for child in widget.winfo_children():
            self._bind_pointer(child)

    def _on_enter(self, _event: tk.Event[tk.Misc]) -> None:
        if self._dimmed or self._selected:
            return
        self.configure(
            width=self._base_width + 10,
            height=self._base_height + 14,
            fg_color="#18232D",
            border_color=self.option.accent,
        )
        self.grid_configure(padx=1, pady=1)
        self.title_label.configure(font=("Inter", 19, "bold"))

    def _on_leave(self, event: tk.Event[tk.Misc]) -> None:
        if self._selected or self._dimmed:
            return
        target = self.winfo_containing(event.x_root, event.y_root)
        if target is not None and self._is_descendant(target):
            return
        self.configure(
            width=self._base_width,
            height=self._base_height,
            fg_color="#111820",
            border_color=BORDER_COLOR,
        )
        self.grid_configure(padx=7, pady=8)
        self.title_label.configure(font=("Inter", 18, "bold"))

    def _is_descendant(self, widget: Any) -> bool:
        current = widget
        while current is not None:
            if current == self:
                return True
            current = getattr(current, "master", None)
        return False

    def _on_click(self, _event: tk.Event[tk.Misc]) -> None:
        self._on_select(self.option)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self._dimmed = False
            self.configure(
                width=self._base_width + 13,
                height=self._base_height + 18,
                fg_color="#13271D",
                border_color=self.option.accent,
            )
            self.title_label.configure(
                text=f"{self.option.title} // SELECTED",
                text_color=self.option.accent,
            )
            self.select_label.configure(text="✓ ВЫБРАНО")
            self.grid_configure(padx=0, pady=0)
            self._pulse(0)
        else:
            self._cancel_pulse()
            self.title_label.configure(
                text=self.option.title,
                text_color="#66717D" if self._dimmed else TEXT_PRIMARY,
            )
            self.select_label.configure(text=f"[{self.option.id.upper()}]")

    def set_dimmed(self, dimmed: bool) -> None:
        self._dimmed = dimmed
        if dimmed:
            self._cancel_pulse()
            self.configure(
                width=self._base_width - 5,
                height=self._base_height - 6,
                fg_color="#0B1015",
                border_color="#20272F",
            )
            self.icon_label.configure(text_color="#3D4650")
            self.title_label.configure(text_color="#59616B")
            self.description_label.configure(text_color="#46505A")
            self.effect_label.configure(text_color="#39424B")
            self.select_label.configure(text_color="#3D4650")
            self.grid_configure(padx=9, pady=12)
        else:
            self.icon_label.configure(text_color=self.option.accent)
            self.description_label.configure(text_color="#C5D0DB")
            self.effect_label.configure(text_color=TEXT_MUTED)
            self.select_label.configure(text_color=self.option.accent)
            if not self._selected:
                self.configure(
                    width=self._base_width,
                    height=self._base_height,
                    fg_color="#111820",
                    border_color=BORDER_COLOR,
                )
                self.title_label.configure(text_color=TEXT_PRIMARY)
                self.grid_configure(padx=7, pady=8)

    def _pulse(self, step: int) -> None:
        self._pulse_job = None
        if not self._selected:
            return
        values = (0.35, 0.65, 1.0, 0.65, 0.4, 0.8, 1.0)
        if step >= len(values):
            self.configure(border_color=self.option.accent, fg_color="#13271D")
            return
        ratio = values[step]
        self.configure(
            border_color=_blend_color("#183128", self.option.accent, ratio),
            fg_color=_blend_color("#10171E", "#193C29", ratio * 0.6),
        )
        self._pulse_job = self.after(75, lambda: self._pulse(step + 1))

    def _cancel_pulse(self) -> None:
        if self._pulse_job is not None:
            try:
                self.after_cancel(self._pulse_job)
            except tk.TclError:
                self._pulse_job = None
            self._pulse_job = None

    def destroy(self) -> None:
        self._cancel_pulse()
        super().destroy()


class SkillSelectWindow(ctk.CTk):
    """Матрица и выбор skill_level до создания главного окна."""

    ENTER_TEXT: Final[str] = "ВОЙТИ В СИСТЕМУ"

    def __init__(self) -> None:
        super().__init__()
        self.title("GreyHat // Инициализация оператора")
        self.configure(fg_color=DARK_BG)
        self.attributes("-fullscreen", True)
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            self.configure(fg_color=DARK_BG)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", self._cancel)
        self.bind("<Return>", self._enter_system)
        for index, option in enumerate(SKILL_OPTIONS, start=1):
            self.bind(
                str(index),
                lambda _event, selected=option: self._select(selected),
            )

        self.selected_skill: str | None = None
        self._selected_option: SkillOption | None = None
        self._glitch_job: str | None = None
        self._fade_job: str | None = None
        self._typing_job: str | None = None
        self._closed = False
        self._random = random.SystemRandom()
        self.cards: dict[str, SkillCard] = {}

        self.matrix_canvas = MatrixRain(
            self,
            background=DARK_BG,
            column_width=24,
            font_size=10,
        )
        self.matrix_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.matrix_canvas.lower()
        self.matrix_canvas.start()

        self._build_heading()
        self._build_cards()
        self._build_enter_area()
        self.after(30, lambda: self._fade_in(0))
        self.after(400, self._glitch_title)

    def _build_heading(self) -> None:
        self.heading_frame = ctk.CTkFrame(
            self,
            fg_color="#0A0F14",
            corner_radius=10,
            border_width=1,
            border_color="#19372A",
            height=130,
        )
        self.heading_frame.place(
            relx=0.5,
            rely=0.12,
            anchor="center",
            relwidth=0.72,
            relheight=0.14,
        )
        self.heading_frame.pack_propagate(False)

        ctk.CTkLabel(
            self.heading_frame,
            text="GREYHAT // CYBERDECK BOOT SEQUENCE",
            text_color=ACCENT_CYAN,
            font=(FONT_MONO_FAMILY, 12, "bold"),
        ).place(relx=0.5, rely=0.2, anchor="center")
        self.glitch_shadow_red = ctk.CTkLabel(
            self.heading_frame,
            text="ИНИЦИАЛИЗАЦИЯ ОПЕРАТОРА...",
            text_color=WARNING_RED,
            font=("Inter", 30, "bold"),
        )
        self.glitch_shadow_red.place(relx=0.501, rely=0.56, anchor="center")
        self.glitch_shadow_cyan = ctk.CTkLabel(
            self.heading_frame,
            text="ИНИЦИАЛИЗАЦИЯ ОПЕРАТОРА...",
            text_color=ACCENT_CYAN,
            font=("Inter", 30, "bold"),
        )
        self.glitch_shadow_cyan.place(relx=0.499, rely=0.56, anchor="center")
        self.title_label = ctk.CTkLabel(
            self.heading_frame,
            text="ИНИЦИАЛИЗАЦИЯ ОПЕРАТОРА...",
            text_color=NEON_GREEN,
            font=("Inter", 30, "bold"),
        )
        self.title_label.place(relx=0.5, rely=0.56, anchor="center")
        self.subtitle_label = ctk.CTkLabel(
            self.heading_frame,
            text="Выберите профиль. Изменить его после входа будет нельзя.",
            text_color=TEXT_MUTED,
            font=("Inter", 12),
        )
        self.subtitle_label.place(relx=0.5, rely=0.86, anchor="center")

    def _build_cards(self) -> None:
        self.cards_frame = ctk.CTkFrame(
            self,
            fg_color="#090E13",
            corner_radius=14,
            border_width=1,
            border_color="#183126",
        )
        self.cards_frame.place(
            relx=0.5,
            rely=0.53,
            anchor="center",
            relwidth=0.96,
            relheight=0.55,
        )
        self.cards_frame.grid_rowconfigure(0, weight=1)
        for column in range(len(SKILL_OPTIONS)):
            self.cards_frame.grid_columnconfigure(column, weight=1, uniform="skill")

        available_width = self.winfo_screenwidth() * 0.96 - 100
        card_width = max(140, min(225, int(available_width / len(SKILL_OPTIONS))))
        available_height = self.winfo_screenheight() * 0.55 - 18
        card_height = max(310, min(390, int(available_height)))
        for column, option in enumerate(SKILL_OPTIONS):
            card = SkillCard(
                self.cards_frame,
                option,
                self._select,
                card_width=card_width,
                card_height=card_height,
            )
            card.grid(row=0, column=column, padx=7, pady=8)
            self.cards[option.id] = card

    def _build_enter_area(self) -> None:
        self.enter_frame = ctk.CTkFrame(
            self,
            fg_color="#0A0F14",
            corner_radius=10,
            border_width=1,
            border_color="#183126",
        )
        self.enter_frame.place(
            relx=0.5,
            rely=0.88,
            anchor="center",
            relwidth=0.5,
            relheight=0.1,
        )
        self.enter_frame.grid_columnconfigure(0, weight=1)
        self.enter_button = ctk.CTkButton(
            self.enter_frame,
            text="",
            height=48,
            state="disabled",
            fg_color=NEON_GREEN,
            hover_color="#00C853",
            text_color=DARK_BG,
            border_width=2,
            border_color=NEON_GREEN,
            font=(FONT_MONO_FAMILY, 15, "bold"),
            command=self._enter_system,
        )
        self.enter_button.grid(row=0, column=0, padx=16, pady=13, sticky="ew")
        self.enter_frame.place_forget()

    def _glitch_title(self) -> None:
        self._glitch_job = None
        if self._closed:
            return
        base = "ИНИЦИАЛИЗАЦИЯ ОПЕРАТОРА..."
        if self._random.random() < 0.32:
            position = self._random.randrange(len(base))
            replacement = self._random.choice(("#", "0", "1", "/", "_"))
            text = f"{base[:position]}{replacement}{base[position + 1 :]}"
            self.title_label.configure(text=text, text_color="#B8FFCD")
            offset = self._random.uniform(-0.004, 0.004)
            self.glitch_shadow_red.place_configure(relx=0.501 + offset)
            self.glitch_shadow_cyan.place_configure(relx=0.499 - offset)
            delay = self._random.randint(55, 100)
        else:
            self.title_label.configure(text=base, text_color=NEON_GREEN)
            self.glitch_shadow_red.place_configure(relx=0.501)
            self.glitch_shadow_cyan.place_configure(relx=0.499)
            delay = self._random.randint(170, 320)
        self._glitch_job = self.after(delay, self._glitch_title)

    def _fade_in(self, step: int) -> None:
        self._fade_job = None
        if self._closed:
            return
        total_steps = 24
        ratio = min(1.0, step / total_steps)
        try:
            self.attributes("-alpha", max(0.04, ratio))
        except tk.TclError:
            self.heading_frame.configure(
                border_color=_blend_color(DARK_BG, "#19372A", ratio)
            )
        if step < total_steps:
            self._fade_job = self.after(28, lambda: self._fade_in(step + 1))

    def _select(self, option: SkillOption) -> None:
        if option.id not in SKILL_LEVELS:
            raise ValueError(f"Неизвестный skill level: {option.id}")
        self._selected_option = option
        for skill_id, card in self.cards.items():
            card.set_dimmed(skill_id != option.id)
            card.set_selected(skill_id == option.id)
        self.subtitle_label.configure(
            text=f"ПРОФИЛЬ {option.title.upper()} ЗАГРУЖЕН // подтвердите вход",
            text_color=option.accent,
        )
        self._show_enter_button(option)

    def _show_enter_button(self, option: SkillOption) -> None:
        if self._typing_job is not None:
            self.after_cancel(self._typing_job)
            self._typing_job = None
        self.enter_frame.place(
            relx=0.5,
            rely=0.88,
            anchor="center",
            relwidth=0.5,
            relheight=0.1,
        )
        self.enter_frame.configure(border_color=option.accent)
        self.enter_button.configure(
            text="",
            state="disabled",
            fg_color=option.accent,
            border_color=option.accent,
        )
        self._type_enter_text(0)

    def _type_enter_text(self, index: int) -> None:
        self._typing_job = None
        if self._closed:
            return
        if index > len(self.ENTER_TEXT):
            self.enter_button.configure(state="normal")
            return
        cursor = "█" if index < len(self.ENTER_TEXT) else ""
        self.enter_button.configure(text=f"> {self.ENTER_TEXT[:index]}{cursor}")
        self._typing_job = self.after(42, lambda: self._type_enter_text(index + 1))

    def _enter_system(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if self._selected_option is None:
            return
        self.selected_skill = self._selected_option.id
        self._shutdown()

    def _cancel(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        self.selected_skill = None
        self._shutdown()

    def _shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.matrix_canvas.stop()
        for job in (
            self._glitch_job,
            self._fade_job,
            self._typing_job,
        ):
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    continue
        self.destroy()

    def run(self) -> str | None:
        self.mainloop()
        return self.selected_skill


__all__ = ["SKILL_OPTIONS", "SkillCard", "SkillOption", "SkillSelectWindow"]
