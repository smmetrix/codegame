"""Офлайн-мини-игры GreyHat: реакция и диалоговое дерево."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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
    WARNING_RED,
)


CAMERA_GAME_ID: Final[str] = "camera_bypass"
SOCIAL_GAME_ID: Final[str] = "social_engineering"


@dataclass(frozen=True, slots=True)
class MinigameResult:
    game_id: str
    success: bool
    score: int
    reward_btc: int
    reward_exp: int
    trace_delta: float
    details: str

    def to_dict(self) -> dict[str, object]:
        return {
            "game_id": self.game_id,
            "success": self.success,
            "score": self.score,
            "reward_btc": self.reward_btc,
            "reward_exp": self.reward_exp,
            "trace_delta": self.trace_delta,
            "details": self.details,
        }


MinigameCallback = Callable[[MinigameResult], None]


class CameraBypassGame:
    """Timing clicker: игрок кликает только во время зеленого кадра."""

    REQUIRED_HITS: Final[int] = 5
    MAX_STRIKES: Final[int] = 3
    REWARD_BTC: Final[int] = 140
    REWARD_EXP: Final[int] = 280

    def __init__(
        self,
        master: Any,
        *,
        on_complete: MinigameCallback | None = None,
        random_source: random.Random | None = None,
    ) -> None:
        import customtkinter as ctk

        self.ctk = ctk
        self._on_complete = on_complete
        self._random = random_source or random.SystemRandom()
        self._successes = 0
        self._strikes = 0
        self._score = 0
        self._waiting_for_safe_frame = False
        self._safe_frame_open = False
        self._safe_frame_started = 0.0
        self._next_frame_job: str | None = None
        self._safe_timeout_job: str | None = None
        self._completed = False
        self._result_sent = False

        self.window = ctk.CTkToplevel(master)
        self.window.title("MiniGame // Camera Bypass")
        self.window.geometry("700x610")
        self.window.minsize(560, 500)
        self.window.configure(fg_color=DARK_BG)
        self.window.transient(master)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            self.window,
            text="ОБХОД КАМЕР НАБЛЮДЕНИЯ",
            text_color=NEON_GREEN,
            font=("Inter", 23, "bold"),
        ).grid(row=0, column=0, padx=24, pady=(22, 3), sticky="w")
        ctk.CTkLabel(
            self.window,
            text=(
                "Кликайте только когда поток сменится на зеленый SAFE FRAME. "
                "Ранний клик или пропущенный кадр повышает Trace."
            ),
            text_color=TEXT_MUTED,
            font=FONT_BODY,
            wraplength=620,
            justify="left",
        ).grid(row=1, column=0, padx=24, pady=(0, 12), sticky="w")

        status = ctk.CTkFrame(self.window, fg_color="transparent")
        status.grid(row=2, column=0, padx=24, pady=3, sticky="ew")
        status.grid_columnconfigure(1, weight=1)
        self.round_label = ctk.CTkLabel(
            status,
            text="HITS 0/5",
            text_color=ACCENT_CYAN,
            font=(FONT_MONO_FAMILY, 12, "bold"),
        )
        self.round_label.grid(row=0, column=0, sticky="w")
        self.progress = ctk.CTkProgressBar(
            status,
            height=9,
            fg_color=DARK_GRAY,
            progress_color=NEON_GREEN,
        )
        self.progress.grid(row=0, column=1, padx=14, sticky="ew")
        self.progress.set(0.0)
        self.strike_label = ctk.CTkLabel(
            status,
            text="TRACE 0/3",
            text_color=TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 12, "bold"),
        )
        self.strike_label.grid(row=0, column=2, sticky="e")

        self.camera_frame = ctk.CTkFrame(
            self.window,
            fg_color="#241015",
            corner_radius=12,
            border_width=3,
            border_color=WARNING_RED,
        )
        self.camera_frame.grid(row=3, column=0, padx=24, pady=14, sticky="nsew")
        self.camera_frame.grid_columnconfigure(0, weight=1)
        self.camera_frame.grid_rowconfigure(0, weight=1)
        self.frame_label = ctk.CTkLabel(
            self.camera_frame,
            text="CAM-07\nSURVEILLANCE ACTIVE",
            text_color=WARNING_RED,
            font=(FONT_MONO_FAMILY, 25, "bold"),
        )
        self.frame_label.grid(row=0, column=0, sticky="nsew")

        controls = ctk.CTkFrame(self.window, fg_color="transparent")
        controls.grid(row=4, column=0, padx=24, pady=(3, 20), sticky="ew")
        controls.grid_columnconfigure(0, weight=1)
        self.action_button = ctk.CTkButton(
            controls,
            text="НАЧАТЬ ПЕРЕХВАТ",
            height=48,
            fg_color=ACCENT_CYAN,
            hover_color="#00AFC2",
            text_color=DARK_BG,
            font=FONT_HEADING,
            command=self._action,
        )
        self.action_button.grid(row=0, column=0, sticky="ew")
        self.feedback_label = ctk.CTkLabel(
            controls,
            text="Ожидается запуск...",
            text_color=TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 11),
        )
        self.feedback_label.grid(row=1, column=0, pady=(7, 0), sticky="ew")

    def _action(self) -> None:
        if self._completed:
            self.window.destroy()
            return
        if not self._waiting_for_safe_frame and not self._safe_frame_open:
            self._begin()
            return
        if self._safe_frame_open:
            reaction_ms = int((time.monotonic() - self._safe_frame_started) * 1_000)
            self._score += max(100, 1_000 - reaction_ms)
            self.feedback_label.configure(
                text=f"FRAME CAPTURED // reaction {reaction_ms} ms",
                text_color=NEON_GREEN,
            )
            self._resolve_round(hit=True)
            return
        self.feedback_label.configure(
            text="TOO EARLY // камера заметила движение", text_color=WARNING_RED
        )
        self._cancel_job("_next_frame_job")
        self._resolve_round(hit=False)

    def _begin(self) -> None:
        self._successes = 0
        self._strikes = 0
        self._score = 0
        self._completed = False
        self.action_button.configure(
            text="ПЕРЕХВАТИТЬ SAFE FRAME", fg_color=WARNING_RED
        )
        self._schedule_next_frame()

    def _schedule_next_frame(self) -> None:
        if self._completed:
            return
        self._waiting_for_safe_frame = True
        self._safe_frame_open = False
        self.camera_frame.configure(fg_color="#241015", border_color=WARNING_RED)
        self.frame_label.configure(
            text="CAM-07\nSURVEILLANCE ACTIVE", text_color=WARNING_RED
        )
        delay = self._random.randint(800, 2_100)
        self._next_frame_job = self.window.after(delay, self._open_safe_frame)

    def _open_safe_frame(self) -> None:
        self._next_frame_job = None
        if self._completed:
            return
        self._waiting_for_safe_frame = False
        self._safe_frame_open = True
        self._safe_frame_started = time.monotonic()
        self.camera_frame.configure(fg_color="#0B2A19", border_color=NEON_GREEN)
        self.frame_label.configure(text="SAFE FRAME\nCLICK NOW", text_color=NEON_GREEN)
        window_ms = max(330, 720 - self._successes * 65)
        self._safe_timeout_job = self.window.after(window_ms, self._miss_safe_frame)

    def _miss_safe_frame(self) -> None:
        self._safe_timeout_job = None
        if not self._safe_frame_open or self._completed:
            return
        self.feedback_label.configure(
            text="FRAME MISSED // Trace increased", text_color=WARNING_RED
        )
        self._resolve_round(hit=False)

    def _resolve_round(self, *, hit: bool) -> None:
        self._cancel_job("_safe_timeout_job")
        self._safe_frame_open = False
        self._waiting_for_safe_frame = False
        if hit:
            self._successes += 1
        else:
            self._strikes += 1
        self._refresh_scoreboard()

        if self._successes >= self.REQUIRED_HITS:
            self._finish(success=True)
        elif self._strikes >= self.MAX_STRIKES:
            self._finish(success=False)
        else:
            # Межкадровая пауза уже считается опасной фазой: повторный клик
            # дает strike, а не перезапускает всю мини-игру.
            self._waiting_for_safe_frame = True
            self._next_frame_job = self.window.after(650, self._schedule_next_frame)

    def _refresh_scoreboard(self) -> None:
        self.round_label.configure(text=f"HITS {self._successes}/{self.REQUIRED_HITS}")
        self.strike_label.configure(
            text=f"TRACE {self._strikes}/{self.MAX_STRIKES}",
            text_color=WARNING_RED if self._strikes else TEXT_MUTED,
        )
        self.progress.set(self._successes / self.REQUIRED_HITS)

    def _finish(self, *, success: bool) -> None:
        self._completed = True
        self._cancel_all_jobs()
        if success:
            details = "Камеры зациклены; маршрут свободен."
            result = MinigameResult(
                game_id=CAMERA_GAME_ID,
                success=True,
                score=self._score,
                reward_btc=self.REWARD_BTC,
                reward_exp=self.REWARD_EXP,
                trace_delta=-15.0,
                details=details,
            )
            color = NEON_GREEN
            title = "BYPASS COMPLETE"
        else:
            details = "Система наблюдения подняла тревогу."
            result = MinigameResult(
                game_id=CAMERA_GAME_ID,
                success=False,
                score=self._score,
                reward_btc=0,
                reward_exp=0,
                trace_delta=25.0,
                details=details,
            )
            color = WARNING_RED
            title = "CAMERA ALERT"
        self.camera_frame.configure(border_color=color)
        self.frame_label.configure(text=title, text_color=color)
        self.feedback_label.configure(text=details, text_color=color)
        self.action_button.configure(
            text="ЗАКРЫТЬ",
            fg_color=color,
            hover_color=color,
            text_color=DARK_BG,
        )
        self._send_result(result)

    def _cancel(self) -> None:
        self._cancel_all_jobs()
        if not self._completed:
            self._send_result(
                MinigameResult(
                    game_id=CAMERA_GAME_ID,
                    success=False,
                    score=self._score,
                    reward_btc=0,
                    reward_exp=0,
                    trace_delta=0.0,
                    details="Мини-игра закрыта игроком.",
                )
            )
        self.window.destroy()

    def _send_result(self, result: MinigameResult) -> None:
        if self._result_sent:
            return
        self._result_sent = True
        if self._on_complete is not None:
            self._on_complete(result)

    def _cancel_job(self, attribute: str) -> None:
        job = getattr(self, attribute)
        if job is not None:
            try:
                self.window.after_cancel(job)
            except Exception:
                job = None
            setattr(self, attribute, None)

    def _cancel_all_jobs(self) -> None:
        self._cancel_job("_next_frame_job")
        self._cancel_job("_safe_timeout_job")


@dataclass(frozen=True, slots=True)
class DialogueChoice:
    id: str
    text: str
    next_node: str
    trust_delta: int


@dataclass(frozen=True, slots=True)
class DialogueNode:
    id: str
    speaker: str
    text: str
    choices: tuple[DialogueChoice, ...]
    terminal_success: bool | None = None


DIALOGUE_TREE: Final[Mapping[str, DialogueNode]] = MappingProxyType(
    {
        "start": DialogueNode(
            id="start",
            speaker="SYSADMIN // ARKADY",
            text=("Ночная смена. Кто вы и почему пишете в закрытый канал поддержки?"),
            choices=(
                DialogueChoice(
                    "polite_ticket",
                    "Добрый вечер. Я из выездной группы, закрываю ваш ticket #7319.",
                    "identity",
                    1,
                ),
                DialogueChoice(
                    "authority",
                    "Центр безопасности. Немедленно выполняйте инструкции.",
                    "identity",
                    -1,
                ),
                DialogueChoice(
                    "threat",
                    "Дайте пароль, иначе вас уволят до рассвета.",
                    "failure",
                    -3,
                ),
            ),
        ),
        "identity": DialogueNode(
            id="identity",
            speaker="SYSADMIN // ARKADY",
            text="Номер похож на настоящий. Какая группа ведет эти работы?",
            choices=(
                DialogueChoice(
                    "noc_team",
                    "NOC-2. Проверяем рассинхронизацию резервного шлюза.",
                    "policy",
                    2,
                ),
                DialogueChoice(
                    "finance_team",
                    "Финансовый отдел. Нам нужен доступ к вашим серверам.",
                    "verification",
                    -1,
                ),
                DialogueChoice(
                    "ask_password_now",
                    "Неважно. Просто пришлите пароль администратора.",
                    "failure",
                    -2,
                ),
            ),
        ),
        "policy": DialogueNode(
            id="policy",
            speaker="SYSADMIN // ARKADY",
            text=(
                "NOC-2 действительно оставляли заявку. Что именно нужно от меня "
                "по регламенту?"
            ),
            choices=(
                DialogueChoice(
                    "readback",
                    "Сверьте одноразовый сервисный код; постоянный пароль не нужен.",
                    "maintenance",
                    2,
                ),
                DialogueChoice(
                    "reset_all",
                    "Сбросьте все учетные записи и отключите журналирование.",
                    "verification",
                    -1,
                ),
                DialogueChoice(
                    "offer_money",
                    "Заплачу 0.1 BTC, если дадите root прямо сейчас.",
                    "failure",
                    -3,
                ),
            ),
        ),
        "verification": DialogueNode(
            id="verification",
            speaker="SYSADMIN // ARKADY",
            text="Это отклоняется от процедуры. Назовите безопасный вариант проверки.",
            choices=(
                DialogueChoice(
                    "recovery_channel",
                    "Используйте временный код из recovery-консоли и сразу отзовите его.",
                    "maintenance",
                    2,
                ),
                DialogueChoice(
                    "disable_security",
                    "Отключите MFA и антивирус — тогда проверка пройдет быстрее.",
                    "failure",
                    -3,
                ),
            ),
        ),
        "maintenance": DialogueNode(
            id="maintenance",
            speaker="SYSADMIN // ARKADY",
            text="Recovery-консоль открыта. Какой следующий безопасный шаг?",
            choices=(
                DialogueChoice(
                    "temporary_code",
                    "Создайте временный код на пять минут и передайте его в этот ticket.",
                    "success",
                    2,
                ),
                DialogueChoice(
                    "permanent_secret",
                    "Отправьте постоянный пароль и не меняйте его после проверки.",
                    "failure",
                    -2,
                ),
            ),
        ),
        "success": DialogueNode(
            id="success",
            speaker="SYSADMIN // ARKADY",
            text=(
                "Код выпущен: TEMP-PASS Aurora#7319. Через пять минут он будет отозван."
            ),
            choices=(),
            terminal_success=True,
        ),
        "failure": DialogueNode(
            id="failure",
            speaker="SECURITY BOT",
            text="Диалог помечен как фишинг. Канал закрыт, Trace увеличен.",
            choices=(),
            terminal_success=False,
        ),
    }
)


class SocialEngineeringSession:
    """Тестируемая модель dialogue tree без зависимости от GUI."""

    def __init__(self) -> None:
        self.current_node_id = "start"
        self.trust = 0
        self.history: list[str] = []
        self.completed = False
        self.success = False

    @property
    def current_node(self) -> DialogueNode:
        return DIALOGUE_TREE[self.current_node_id]

    def choose(self, choice_id: str) -> DialogueNode:
        if self.completed:
            raise RuntimeError("Диалог уже завершен")
        choice = next(
            (item for item in self.current_node.choices if item.id == choice_id), None
        )
        if choice is None:
            raise KeyError(f"Реплика {choice_id!r} недоступна в текущем узле")
        self.history.append(choice.id)
        self.trust = max(-3, min(7, self.trust + choice.trust_delta))
        target = choice.next_node
        if self.trust <= -3:
            target = "failure"
        elif target == "success" and self.trust < 3:
            target = "failure"
        self.current_node_id = target
        terminal = self.current_node.terminal_success
        if terminal is not None:
            self.completed = True
            self.success = terminal
        return self.current_node

    def reset(self) -> None:
        self.current_node_id = "start"
        self.trust = 0
        self.history.clear()
        self.completed = False
        self.success = False


class SocialEngineeringGame:
    """CustomTkinter dialogue tree для получения временного service password."""

    REWARD_BTC: Final[int] = 190
    REWARD_EXP: Final[int] = 360

    def __init__(
        self,
        master: Any,
        *,
        on_complete: MinigameCallback | None = None,
    ) -> None:
        import customtkinter as ctk

        self.ctk = ctk
        self._on_complete = on_complete
        self._result_sent = False
        self.session = SocialEngineeringSession()

        self.window = ctk.CTkToplevel(master)
        self.window.title("MiniGame // Social Engineering")
        self.window.geometry("780x690")
        self.window.minsize(620, 560)
        self.window.configure(fg_color=DARK_BG)
        self.window.transient(master)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            self.window,
            text="СОЦИАЛЬНАЯ ИНЖЕНЕРИЯ",
            text_color=ACCENT_CYAN,
            font=("Inter", 23, "bold"),
        ).grid(row=0, column=0, padx=24, pady=(22, 3), sticky="w")
        ctk.CTkLabel(
            self.window,
            text=(
                "Учебный диалог: укрепляйте доверие, не просите постоянные пароли "
                "и придерживайтесь безопасной процедуры временного доступа."
            ),
            text_color=TEXT_MUTED,
            font=FONT_BODY,
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, padx=24, pady=(0, 12), sticky="w")

        trust_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        trust_frame.grid(row=2, column=0, padx=24, pady=4, sticky="ew")
        trust_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            trust_frame,
            text="TRUST",
            text_color=TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 11, "bold"),
        ).grid(row=0, column=0, padx=(0, 10))
        self.trust_progress = ctk.CTkProgressBar(
            trust_frame,
            height=10,
            fg_color=DARK_GRAY,
            progress_color=ACCENT_CYAN,
        )
        self.trust_progress.grid(row=0, column=1, sticky="ew")
        self.trust_label = ctk.CTkLabel(
            trust_frame,
            text="0",
            width=35,
            text_color=ACCENT_CYAN,
            font=(FONT_MONO_FAMILY, 11, "bold"),
        )
        self.trust_label.grid(row=0, column=2, padx=(10, 0))

        conversation = ctk.CTkFrame(
            self.window,
            fg_color=DARK_GRAY,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        conversation.grid(row=3, column=0, padx=24, pady=12, sticky="nsew")
        conversation.grid_columnconfigure(0, weight=1)
        conversation.grid_rowconfigure(1, weight=1)
        self.speaker_label = ctk.CTkLabel(
            conversation,
            text="",
            text_color=NEON_GREEN,
            font=(FONT_MONO_FAMILY, 11, "bold"),
            anchor="w",
        )
        self.speaker_label.grid(row=0, column=0, padx=18, pady=(16, 4), sticky="ew")
        self.dialogue_label = ctk.CTkLabel(
            conversation,
            text="",
            text_color=TEXT_PRIMARY,
            font=("Inter", 16),
            wraplength=680,
            justify="left",
            anchor="nw",
        )
        self.dialogue_label.grid(row=1, column=0, padx=18, pady=(4, 14), sticky="nsew")

        self.choice_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        self.choice_frame.grid(row=4, column=0, padx=24, pady=(0, 20), sticky="ew")
        self.choice_frame.grid_columnconfigure(0, weight=1)
        self._render_node()

    def _render_node(self) -> None:
        for child in self.choice_frame.winfo_children():
            child.destroy()
        node = self.session.current_node
        self.speaker_label.configure(text=node.speaker)
        self.dialogue_label.configure(text=node.text)
        self.trust_progress.set((self.session.trust + 3) / 10)
        self.trust_label.configure(
            text=f"{self.session.trust:+d}",
            text_color=NEON_GREEN if self.session.trust >= 3 else ACCENT_CYAN,
        )

        if node.terminal_success is not None:
            self._finish(node.terminal_success)
            return
        for row, choice in enumerate(node.choices):
            prefix = "+" if choice.trust_delta > 0 else "•"
            button = self.ctk.CTkButton(
                self.choice_frame,
                text=f"{prefix} {choice.text}",
                height=48,
                anchor="w",
                fg_color="#10232A",
                hover_color="#16404B",
                border_width=1,
                border_color=ACCENT_CYAN,
                text_color=TEXT_PRIMARY,
                font=("Inter", 13),
                command=lambda choice_id=choice.id: self._choose(choice_id),
            )
            button.grid(row=row, column=0, pady=4, sticky="ew")

    def _choose(self, choice_id: str) -> None:
        self.session.choose(choice_id)
        self._render_node()

    def _finish(self, success: bool) -> None:
        if success:
            result = MinigameResult(
                game_id=SOCIAL_GAME_ID,
                success=True,
                score=max(0, self.session.trust * 250),
                reward_btc=self.REWARD_BTC,
                reward_exp=self.REWARD_EXP,
                trace_delta=-10.0,
                details="Получен временный код Aurora#7319 без постоянного пароля.",
            )
            color = NEON_GREEN
            button_text = "ДИАЛОГ ЗАВЕРШЕН // ЗАКРЫТЬ"
        else:
            result = MinigameResult(
                game_id=SOCIAL_GAME_ID,
                success=False,
                score=0,
                reward_btc=0,
                reward_exp=0,
                trace_delta=20.0,
                details="Сисадмин распознал подозрительный запрос.",
            )
            color = WARNING_RED
            button_text = "КАНАЛ ЗАКРЫТ // ПОПРОБОВАТЬ СНОВА"

        self.speaker_label.configure(text_color=color)
        self.trust_progress.configure(progress_color=color)
        action = self.window.destroy if success else self._retry
        self.ctk.CTkButton(
            self.choice_frame,
            text=button_text,
            height=46,
            fg_color=color,
            hover_color=color,
            text_color=DARK_BG,
            font=FONT_HEADING,
            command=action,
        ).grid(row=0, column=0, sticky="ew")
        self._send_result(result)

    def _retry(self) -> None:
        self._result_sent = False
        self.session.reset()
        self._render_node()

    def _cancel(self) -> None:
        if not self.session.completed:
            self._send_result(
                MinigameResult(
                    game_id=SOCIAL_GAME_ID,
                    success=False,
                    score=0,
                    reward_btc=0,
                    reward_exp=0,
                    trace_delta=0.0,
                    details="Мини-игра закрыта игроком.",
                )
            )
        self.window.destroy()

    def _send_result(self, result: MinigameResult) -> None:
        if self._result_sent:
            return
        self._result_sent = True
        if self._on_complete is not None:
            self._on_complete(result)


__all__ = [
    "CAMERA_GAME_ID",
    "DIALOGUE_TREE",
    "DialogueChoice",
    "DialogueNode",
    "MinigameCallback",
    "MinigameResult",
    "SOCIAL_GAME_ID",
    "CameraBypassGame",
    "SocialEngineeringGame",
    "SocialEngineeringSession",
]
