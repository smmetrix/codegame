"""DarkNet-магазин и эффекты улучшений GreyHat Cyberdeck."""

from __future__ import annotations

import random
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
from game_state import GameState, InsufficientFundsError
from missions_db import Mission, MissionTier


VPN_PROXY_ID: Final[str] = "vpn_proxy_v2"
AI_COPILOT_ID: Final[str] = "python_ai_copilot"
OVERCLOCKED_CPU_ID: Final[str] = "overclocked_cpu"
BRUTEFORCE_TOOLKIT_ID: Final[str] = "bruteforce_toolkit"


class DarkNetShopError(Exception):
    """Базовая ошибка магазина."""


class UpgradeNotOwnedError(DarkNetShopError):
    """Эффект вызван до покупки соответствующего улучшения."""


@dataclass(frozen=True, slots=True)
class Upgrade:
    id: str
    name: str
    description: str
    price_btc: int
    effect_label: str
    icon: str

    def __post_init__(self) -> None:
        if not self.id or not self.name.strip():
            raise ValueError("Upgrade id и name не могут быть пустыми")
        if isinstance(self.price_btc, bool) or not isinstance(self.price_btc, int):
            raise TypeError("price_btc должен быть целым числом")
        if self.price_btc < 0:
            raise ValueError("price_btc не может быть отрицательным")


@dataclass(frozen=True, slots=True)
class PurchaseResult:
    success: bool
    upgrade: Upgrade
    spent_btc: int
    balance_btc: int
    message: str


@dataclass(frozen=True, slots=True)
class CodePatch:
    old: str
    new: str
    explanation: str


@dataclass(frozen=True, slots=True)
class OverclockResult:
    applied: bool
    code: str
    explanation: str


UPGRADES: Final[tuple[Upgrade, ...]] = (
    Upgrade(
        id=VPN_PROXY_ID,
        name="VPN Прокси v2.0",
        description=(
            "Перенаправляет виртуальный trace через цепочку офлайн-узлов. "
            "Каждая timed mission получает дополнительные 20 секунд."
        ),
        price_btc=180,
        effect_label="+20 секунд к таймеру",
        icon="VPN",
    ),
    Upgrade(
        id=AI_COPILOT_ID,
        name="Python AI Copilot",
        description=(
            "Добавляет к обычной подсказке правильный синтаксический шаблон "
            "для темы текущей миссии, не раскрывая готовый ответ целиком."
        ),
        price_btc=350,
        effect_label="Расширенные подсказки",
        icon="AI",
    ),
    Upgrade(
        id=OVERCLOCKED_CPU_ID,
        name="Overclocked CPU",
        description=(
            "Один раз по команде исправляет случайный незавершенный шаг "
            "в коде текущей миссии. Уже исправленные строки не перезаписываются."
        ),
        price_btc=500,
        effect_label="Автоматизация одного шага",
        icon="CPU",
    ),
    Upgrade(
        id=BRUTEFORCE_TOOLKIT_ID,
        name="BruteForce Toolkit",
        description=(
            "Открывает bonus API в Sandbox: bruteforce_pin(), "
            "generate_wordlist(), hash_md5() и decode_base64()."
        ),
        price_btc=800,
        effect_label="4 бонусные Sandbox-функции",
        icon="BF",
    ),
)

UPGRADE_BY_ID: Final[Mapping[str, Upgrade]] = MappingProxyType(
    {upgrade.id: upgrade for upgrade in UPGRADES}
)

_COPILOT_SYNTAX: Final[Mapping[MissionTier, str]] = MappingProxyType(
    {
        MissionTier.SCRIPT_KIDDIE: (
            "СИНТАКСИС COPILOT:\n"
            "value = 42\n"
            'text = "ghost"\n'
            "if value == 42:\n"
            '    print(f"ACCESS: {text}")'
        ),
        MissionTier.CODE_BREAKER: (
            "СИНТАКСИС COPILOT:\n"
            "index = 0\n"
            "while index < len(items):\n"
            "    item = items[index]\n"
            "    index += 1\n\n"
            "for item in items:\n"
            "    result.append(item)"
        ),
        MissionTier.DATA_HUNTER: (
            "СИНТАКСИС COPILOT:\n"
            'key, value = line.split("|", 1)\n'
            "stats[key] = stats.get(key, 0) + 1\n"
            "clean = value.strip().lower()"
        ),
        MissionTier.EXPLOIT_MASTER: (
            "СИНТАКСИС COPILOT:\n"
            "def transform(data):\n"
            "    result = data.strip()\n"
            "    return result\n\n"
            "output = transform(input_data)"
        ),
        MissionTier.NETWORK_GHOST: (
            "СИНТАКСИС COPILOT:\n"
            "def worker(chunk):\n"
            "    for candidate in chunk:\n"
            "        if check(candidate):\n"
            "            return candidate\n"
            "    return None"
        ),
    }
)

_OVERCLOCK_PATCHES: Final[Mapping[str, tuple[CodePatch, ...]]] = MappingProxyType(
    {
        "m01_smart_bulb": (
            CodePatch('device = "UNKNOWN"', 'device = "LAMP-7"', "Указан id лампы."),
            CodePatch("brightness = 0", "brightness = 100", "Яркость поднята до 100."),
            CodePatch(
                "print(device)",
                'print(f"{device} brightness={brightness}% action={choice}")',
                "Вывод собран f-строкой.",
            ),
        ),
        "m02_sensor_types": (
            CodePatch('temperature = "23.5"', "temperature = 23.5", "Выбран float."),
            CodePatch('online = "True"', "online = True", "Выбран bool."),
            CodePatch('retries = "3"', "retries = 3", "Выбран int."),
            CodePatch('room = "unknown"', 'room = "kitchen"', "Указана комната."),
        ),
        "m03_pin_bypass": (
            CodePatch("entered_pin = 0", "entered_pin = 7319", "Введен найденный PIN."),
            CodePatch(
                "# Сравни entered_pin со stored_pin через if/else.",
                "if entered_pin == stored_pin:\n"
                "    access = True\n"
                '    message = "ACCESS GRANTED"\n'
                "else:\n"
                "    access = False\n"
                '    message = "ACCESS DENIED"',
                "Добавлена развилка авторизации.",
            ),
        ),
        "m04_block_list": (
            CodePatch(
                "# Перебери attempts и добавь IP неуспешных входов.",
                "for entry in attempts:\n"
                '    if entry["success"] is False:\n'
                '        blocked_ips.append(entry["ip"])',
                "Добавлена фильтрация попыток.",
            ),
            CodePatch(
                "failed_count = 0",
                "failed_count = len(blocked_ips)",
                "Счетчик связан с длиной списка.",
            ),
        ),
        "m05_password_bruteforce": (
            CodePatch(
                "checksum = 0",
                "checksum = sum((i + 1) * ord(char) for i, char in enumerate(candidate)) % 997",
                "Добавлена checksum кандидата.",
            ),
            CodePatch(
                "# Вычисли checksum, увеличь attempts и проверь результат.",
                "attempts += 1\n"
                "    if checksum == target_checksum:\n"
                "        password = candidate\n"
                "        break",
                "Добавлена проверка и остановка while.",
            ),
        ),
        "m06_subnet_scanner": (
            CodePatch(
                "hosts = []",
                'hosts = [f"10.13.37.{n}" for n in range(1, 6)]',
                "Сгенерированы адреса подсети.",
            ),
            CodePatch(
                "# Создай пять IP, просканируй каждый и найди узлы с портом 22.",
                "for host in hosts:\n"
                "    ports = scan_ports(host)\n"
                "    scan_report[host] = ports\n"
                "    if 22 in ports:\n"
                "        vulnerable_hosts.append(host)",
                "Добавлен цикл сканирования.",
            ),
        ),
        "m07_database_roles": (
            CodePatch(
                "# Сгруппируй username по role.",
                "for record in records:\n"
                '    role = record["role"]\n'
                '    users_by_role.setdefault(role, []).append(record["username"])',
                "Добавлена группировка по роли.",
            ),
            CodePatch(
                "record_count = 0",
                "record_count = len(records)",
                "Подсчитаны записи.",
            ),
        ),
        "m08_contact_cleanup": (
            CodePatch(
                "# Очисти, проверь и сгруппируй адреса.",
                "for raw in raw_contacts:\n"
                "    email = raw.strip().lower()\n"
                '    if email.count("@") != 1:\n'
                "        continue\n"
                '    name, domain = email.split("@")\n'
                '    if "." in domain:\n'
                "        normalized_emails.append(email)\n"
                "        domains[domain] = domains.get(domain, 0) + 1",
                "Добавлена очистка email.",
            ),
        ),
        "m09_log_filter": (
            CodePatch(
                "# Раздели строки, обнови счетчики и собери ERROR.",
                "for line in logs:\n"
                '    level, service, message = line.split("|", 2)\n'
                "    level_count[level] = level_count.get(level, 0) + 1\n"
                '    if level == "ERROR":\n'
                "        error_messages.append(message)",
                "Добавлен парсер уровней логов.",
            ),
        ),
        "m10_caesar_function": (
            CodePatch(
                "return text",
                "return decrypt_caesar(text, amount)",
                "Функция теперь возвращает расшифровку.",
            ),
        ),
        "m11_base64_decoder": (
            CodePatch(
                'return encoded_bytes.decode("ascii")',
                'return base64.b64decode(encoded_bytes).decode("utf-8")',
                "Добавлено Base64-декодирование.",
            ),
            CodePatch(
                'key = ""',
                'key = decoded.split(":", 1)[1]',
                "Извлечена часть после двоеточия.",
            ),
        ),
        "m12_md5_cracker": (
            CodePatch(
                'digest = ""',
                'digest = hashlib.md5(candidate.encode("utf-8")).hexdigest()',
                "Добавлено вычисление MD5.",
            ),
        ),
        "m13_threaded_bruteforce": (
            CodePatch(
                "# Создай четыре потока со срезами candidates[worker_id::4].\n"
                "# Затем start() каждый поток и отдельным циклом вызови join().",
                "for worker_id in range(4):\n"
                "    chunk = candidates[worker_id::4]\n"
                "    thread = threading.Thread(target=worker, args=(chunk,))\n"
                "    threads.append(thread)\n"
                "for thread in threads:\n"
                "    thread.start()\n"
                "for thread in threads:\n"
                "    thread.join()",
                "Созданы, запущены и синхронизированы четыре потока.",
            ),
        ),
        "m14_bank_firewall": (
            CodePatch(
                "# Для каждого порта запиши allowed или blocked.",
                "for port in ports:\n"
                '        policy[port] = "allowed" if port in (443, 8443) else "blocked"',
                "Построена политика портов.",
            ),
            CodePatch(
                "# Найди разрешенный порт и вызови send_payload().",
                'allowed_ports = [port for port, status in firewall_policy.items() if status == "allowed"]\n'
                "bypass_port = min(allowed_ports)\n"
                'receipt = send_payload(target, "audit:firewall-bypass")',
                "Выбран разрешенный порт и отправлен audit payload.",
            ),
        ),
        "m15_final_choice": (
            CodePatch(
                'choice = "undecided"',
                'choice = "help"',
                "Выбран белый путь; решение можно изменить на sell.",
            ),
        ),
    }
)


class DarkNetShop:
    """Логика магазина, независимая от графического окна."""

    TIMER_BONUS_SECONDS: Final[int] = 20

    def __init__(self, game_state: GameState) -> None:
        if not isinstance(game_state, GameState):
            raise TypeError("game_state должен быть экземпляром GameState")
        self.game_state = game_state

    def get_upgrade(self, upgrade_id: str) -> Upgrade:
        try:
            return UPGRADE_BY_ID[upgrade_id]
        except KeyError as exc:
            raise KeyError(f"Неизвестное улучшение: {upgrade_id}") from exc

    def is_owned(self, upgrade_id: str) -> bool:
        self.get_upgrade(upgrade_id)
        return upgrade_id in self.game_state.purchased_upgrades

    def available_upgrades(self) -> tuple[Upgrade, ...]:
        return tuple(upgrade for upgrade in UPGRADES if not self.is_owned(upgrade.id))

    def purchase(self, upgrade_id: str) -> PurchaseResult:
        upgrade = self.get_upgrade(upgrade_id)
        if self.is_owned(upgrade_id):
            return PurchaseResult(
                success=False,
                upgrade=upgrade,
                spent_btc=0,
                balance_btc=self.game_state.bitcoins,
                message=f"{upgrade.name} уже установлен.",
            )
        try:
            purchased = self.game_state.purchase_upgrade(upgrade.id, upgrade.price_btc)
        except InsufficientFundsError as exc:
            return PurchaseResult(
                success=False,
                upgrade=upgrade,
                spent_btc=0,
                balance_btc=self.game_state.bitcoins,
                message=str(exc),
            )
        if not purchased:
            raise DarkNetShopError("GameState отклонил новую покупку без причины")
        return PurchaseResult(
            success=True,
            upgrade=upgrade,
            spent_btc=upgrade.price_btc,
            balance_btc=self.game_state.bitcoins,
            message=f"Установлено: {upgrade.name}",
        )

    @property
    def timer_bonus_seconds(self) -> int:
        return self.TIMER_BONUS_SECONDS if self.is_owned(VPN_PROXY_ID) else 0

    @property
    def copilot_enabled(self) -> bool:
        return self.is_owned(AI_COPILOT_ID)

    @property
    def overclock_enabled(self) -> bool:
        return self.is_owned(OVERCLOCKED_CPU_ID)

    @property
    def bruteforce_toolkit_enabled(self) -> bool:
        return self.is_owned(BRUTEFORCE_TOOLKIT_ID)

    def copilot_hint(self, mission: Mission) -> str:
        if not self.copilot_enabled:
            raise UpgradeNotOwnedError("Сначала купите Python AI Copilot")
        return f"{mission.hint}\n\n{_COPILOT_SYNTAX[mission.tier]}"

    def apply_overclock_step(
        self,
        mission_id: str,
        code: str,
        *,
        random_source: random.Random | None = None,
    ) -> OverclockResult:
        if not self.overclock_enabled:
            raise UpgradeNotOwnedError("Сначала купите Overclocked CPU")
        if not isinstance(code, str):
            raise TypeError("code должен быть строкой")
        patches = _OVERCLOCK_PATCHES.get(mission_id, ())
        applicable = [patch for patch in patches if patch.old in code]
        if not applicable:
            return OverclockResult(
                applied=False,
                code=code,
                explanation="CPU не нашел незавершенный известный шаг в текущем коде.",
            )
        generator = random_source or random.SystemRandom()
        selected = generator.choice(applicable)
        patched_code = code.replace(selected.old, selected.new, 1)
        return OverclockResult(
            applied=True,
            code=patched_code,
            explanation=selected.explanation,
        )


PurchaseCallback = Callable[[PurchaseResult], None]


class DarkNetShopWindow:
    """CustomTkinter-окно магазина с live-обновлением баланса."""

    def __init__(
        self,
        master: Any,
        shop: DarkNetShop,
        *,
        on_purchase: PurchaseCallback | None = None,
    ) -> None:
        import customtkinter as ctk

        self.ctk = ctk
        self.shop = shop
        self._on_purchase = on_purchase
        self.window = ctk.CTkToplevel(master)
        self.window.title("DarkNet // GreyHat Upgrades")
        self.window.geometry("720x650")
        self.window.minsize(560, 480)
        self.window.configure(fg_color=DARK_BG)
        self.window.transient(master)
        self.window.grab_set()
        self.window.grid_columnconfigure(0, weight=1)
        self.window.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.window,
            text="DARKNET // HARDWARE MARKET",
            text_color=NEON_GREEN,
            font=("Inter", 22, "bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=22, pady=(18, 3), sticky="ew")

        top = ctk.CTkFrame(self.window, fg_color="transparent")
        top.grid(row=1, column=0, padx=22, pady=(0, 10), sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            top,
            text="Только офлайн-модули. Покупки сохраняются автоматически.",
            text_color=TEXT_MUTED,
            font=FONT_BODY,
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.balance_label = ctk.CTkLabel(
            top,
            text="",
            text_color=ACCENT_CYAN,
            font=FONT_HEADING,
            anchor="e",
        )
        self.balance_label.grid(row=0, column=1, sticky="e")

        self.market = ctk.CTkScrollableFrame(
            self.window,
            fg_color="transparent",
            scrollbar_button_color=BORDER_COLOR,
            scrollbar_button_hover_color=ACCENT_CYAN,
        )
        self.market.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="nsew")
        self.market.grid_columnconfigure(0, weight=1)

        self.message_label = ctk.CTkLabel(
            self.window,
            text="SELECT UPGRADE",
            text_color=TEXT_MUTED,
            font=(FONT_MONO_FAMILY, 11),
        )
        self.message_label.grid(row=3, column=0, padx=20, pady=(2, 14), sticky="ew")
        self._render_market()

    def _render_market(self) -> None:
        for child in self.market.winfo_children():
            child.destroy()
        self.balance_label.configure(text=f"{self.shop.game_state.bitcoins} BTC")
        for row, upgrade in enumerate(UPGRADES):
            self._create_upgrade_card(row, upgrade)

    def _create_upgrade_card(self, row: int, upgrade: Upgrade) -> None:
        ctk = self.ctk
        owned = self.shop.is_owned(upgrade.id)
        card = ctk.CTkFrame(
            self.market,
            fg_color=DARK_GRAY,
            corner_radius=8,
            border_width=1,
            border_color=NEON_GREEN if owned else BORDER_COLOR,
        )
        card.grid(row=row, column=0, padx=5, pady=6, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card,
            text=upgrade.icon,
            width=52,
            height=52,
            fg_color="#0C2D20" if owned else DARK_BG,
            corner_radius=6,
            text_color=NEON_GREEN if owned else ACCENT_CYAN,
            font=(FONT_MONO_FAMILY, 14, "bold"),
        ).grid(row=0, column=0, rowspan=3, padx=12, pady=12)
        ctk.CTkLabel(
            card,
            text=upgrade.name,
            text_color=TEXT_PRIMARY,
            font=FONT_HEADING,
            anchor="w",
        ).grid(row=0, column=1, padx=3, pady=(10, 1), sticky="ew")
        ctk.CTkLabel(
            card,
            text=upgrade.description,
            text_color=TEXT_MUTED,
            font=FONT_BODY,
            wraplength=420,
            justify="left",
            anchor="w",
        ).grid(row=1, column=1, padx=3, pady=2, sticky="ew")
        ctk.CTkLabel(
            card,
            text=upgrade.effect_label,
            text_color=NEON_GREEN,
            font=(FONT_MONO_FAMILY, 10),
            anchor="w",
        ).grid(row=2, column=1, padx=3, pady=(1, 10), sticky="ew")

        button = ctk.CTkButton(
            card,
            text="INSTALLED" if owned else f"BUY\n{upgrade.price_btc} BTC",
            width=105,
            height=58,
            state="disabled" if owned else "normal",
            fg_color=BORDER_COLOR if owned else NEON_GREEN,
            hover_color="#00C853",
            text_color=TEXT_MUTED if owned else DARK_BG,
            font=("Inter", 11, "bold"),
            command=lambda upgrade_id=upgrade.id: self._purchase(upgrade_id),
        )
        button.grid(row=0, column=2, rowspan=3, padx=12, pady=12)

    def _purchase(self, upgrade_id: str) -> None:
        result = self.shop.purchase(upgrade_id)
        self.message_label.configure(
            text=result.message,
            text_color=NEON_GREEN if result.success else WARNING_RED,
        )
        self._render_market()
        if self._on_purchase is not None:
            self._on_purchase(result)

    def focus(self) -> None:
        self.window.focus_force()


__all__ = [
    "AI_COPILOT_ID",
    "BRUTEFORCE_TOOLKIT_ID",
    "CodePatch",
    "DarkNetShop",
    "DarkNetShopError",
    "DarkNetShopWindow",
    "OVERCLOCKED_CPU_ID",
    "OverclockResult",
    "PurchaseCallback",
    "PurchaseResult",
    "UPGRADES",
    "UPGRADE_BY_ID",
    "Upgrade",
    "UpgradeNotOwnedError",
    "VPN_PROXY_ID",
]
