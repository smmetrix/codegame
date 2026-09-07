"""Сюжетная база миссий GreyHat: Python Cyberdeck.

Миссии не выполняют реальных сетевых атак. Все сетевые действия используют
детерминированные офлайн-хелперы из :mod:`sandbox`. Валидаторы принимают
``SandboxResult`` и проверяют фактический stdout и созданные переменные, а не
текст пользовательской программы.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass, replace
from enum import IntEnum
from types import MappingProxyType
from typing import Callable, Final, Mapping

from game_state import SKILL_LEVELS
from sandbox import SandboxResult, scan_ports, send_payload


class MissionTier(IntEnum):
    """Пять этапов роста игрока."""

    SCRIPT_KIDDIE = 1
    CODE_BREAKER = 2
    DATA_HUNTER = 3
    EXPLOIT_MASTER = 4
    NETWORK_GHOST = 5


TIER_NAMES: Final[Mapping[MissionTier, str]] = MappingProxyType(
    {
        MissionTier.SCRIPT_KIDDIE: "Скрипт-кидди",
        MissionTier.CODE_BREAKER: "Взломщик кода",
        MissionTier.DATA_HUNTER: "Охотник за данными",
        MissionTier.EXPLOIT_MASTER: "Мастер эксплойтов",
        MissionTier.NETWORK_GHOST: "Призрак Сети",
    }
)

MissionValidator = Callable[[SandboxResult], bool]


@dataclass(frozen=True, slots=True)
class Mission:
    """Полное описание одной учебной сюжетной миссии."""

    id: str
    title: str
    tier: MissionTier
    description: str
    tutorial_text: str
    starter_code: str
    hint: str
    reward_exp: int
    reward_btc: int
    karma_choice: str
    time_limit: int
    validator_func: MissionValidator
    senior_trap: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.id.replace("_", "").isalnum():
            raise ValueError("id миссии должен состоять из букв, цифр и подчеркиваний")
        if not self.title.strip():
            raise ValueError("title миссии не может быть пустым")
        if not isinstance(self.tier, MissionTier):
            raise TypeError("tier должен быть значением MissionTier")
        for field_name in (
            "description",
            "starter_code",
            "hint",
            "karma_choice",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} должен быть непустой строкой")
        if not isinstance(self.tutorial_text, str):
            raise TypeError("tutorial_text должен быть строкой")
        for field_name in ("reward_exp", "reward_btc", "time_limit"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} должен быть целым числом")
            if value < 0:
                raise ValueError(f"{field_name} не может быть отрицательным")
        if not callable(self.validator_func):
            raise TypeError("validator_func должен быть вызываемой функцией")
        if not isinstance(self.senior_trap, str):
            raise TypeError("senior_trap должен быть строкой")

    @property
    def tier_name(self) -> str:
        return TIER_NAMES[self.tier]

    def validate(self, result: SandboxResult) -> bool:
        """Безопасно запускает валидатор для результата песочницы."""

        if not isinstance(result, SandboxResult) or not result.success:
            return False
        try:
            return bool(self.validator_func(result))
        except (KeyError, TypeError, ValueError, IndexError):
            return False


def _clean_stdout(result: SandboxResult) -> str:
    return result.output.replace("\r\n", "\n").strip()


def _has_exact_keys(value: object, expected: Mapping[object, object]) -> bool:
    return type(value) is dict and value == dict(expected)


# ---------------------------------------------------------------------------
# Tier 1 validators: print, variables, primitive types, if/else
# ---------------------------------------------------------------------------


def _validate_mission_01(result: SandboxResult) -> bool:
    variables = result.variables
    choice = variables.get("choice")
    expected_line = f"LAMP-7 brightness=100% action={choice}"
    return (
        variables.get("device") == "LAMP-7"
        and type(variables.get("brightness")) is int
        and variables.get("brightness") == 100
        and choice in {"help", "sell"}
        and _clean_stdout(result) == expected_line
    )


def _validate_mission_02(result: SandboxResult) -> bool:
    variables = result.variables
    return (
        type(variables.get("temperature")) is float
        and variables.get("temperature") == 23.5
        and type(variables.get("online")) is bool
        and variables.get("online") is True
        and type(variables.get("retries")) is int
        and variables.get("retries") == 3
        and variables.get("room") == "kitchen"
        and _clean_stdout(result) == "TEMP=23.5 ONLINE=True RETRIES=3 ROOM=kitchen"
    )


def _validate_mission_03(result: SandboxResult) -> bool:
    variables = result.variables
    return (
        variables.get("stored_pin") == 7319
        and variables.get("entered_pin") == 7319
        and variables.get("access") is True
        and variables.get("message") == "ACCESS GRANTED"
        and _clean_stdout(result) == "ACCESS GRANTED"
    )


# ---------------------------------------------------------------------------
# Tier 2 validators: lists and for/while loops
# ---------------------------------------------------------------------------


def _validate_mission_04(result: SandboxResult) -> bool:
    variables = result.variables
    return (
        variables.get("blocked_ips") == ["10.0.0.8", "10.0.0.3"]
        and variables.get("failed_count") == 2
        and _clean_stdout(result) == "BLOCKED: 2"
    )


def _validate_mission_05(result: SandboxResult) -> bool:
    variables = result.variables
    return (
        variables.get("password") == "neonfox"
        and type(variables.get("attempts")) is int
        and variables.get("attempts") == 4
        and _clean_stdout(result) == "PASSWORD: neonfox ATTEMPTS: 4"
    )


_SUBNET_HOSTS: Final[tuple[str, ...]] = tuple(
    f"10.13.37.{host_number}" for host_number in range(1, 6)
)
_EXPECTED_SUBNET_REPORT: Final[Mapping[str, list[int]]] = MappingProxyType(
    {host: scan_ports(host) for host in _SUBNET_HOSTS}
)
_EXPECTED_VULNERABLE_HOSTS: Final[list[str]] = [
    host for host, ports in _EXPECTED_SUBNET_REPORT.items() if 22 in ports
]


def _validate_mission_06(result: SandboxResult) -> bool:
    variables = result.variables
    return (
        variables.get("hosts") == list(_SUBNET_HOSTS)
        and variables.get("scan_report") == dict(_EXPECTED_SUBNET_REPORT)
        and variables.get("vulnerable_hosts") == _EXPECTED_VULNERABLE_HOSTS
        and variables.get("choice") in {"help", "sell"}
        and _clean_stdout(result) == f"VULNERABLE: {len(_EXPECTED_VULNERABLE_HOSTS)}"
    )


# ---------------------------------------------------------------------------
# Tier 3 validators: dictionaries and string methods
# ---------------------------------------------------------------------------


def _validate_mission_07(result: SandboxResult) -> bool:
    expected = {
        "admin": ["mira"],
        "user": ["lev", "sonya"],
        "guest": ["service-bot"],
    }
    return (
        _has_exact_keys(result.variables.get("users_by_role"), expected)
        and result.variables.get("record_count") == 4
        and _clean_stdout(result) == "ROLES: 3 RECORDS: 4"
    )


def _validate_mission_08(result: SandboxResult) -> bool:
    expected_contacts = [
        "mira@example.com",
        "lev@greyhat.io",
        "sonya@example.com",
    ]
    expected_domains = {"example.com": 2, "greyhat.io": 1}
    return (
        result.variables.get("normalized_emails") == expected_contacts
        and _has_exact_keys(result.variables.get("domains"), expected_domains)
        and _clean_stdout(result) == "VALID: 3"
    )


def _validate_mission_09(result: SandboxResult) -> bool:
    expected_levels = {"INFO": 2, "WARNING": 1, "ERROR": 2}
    expected_errors = ["invalid token", "database timeout"]
    variables = result.variables
    return (
        _has_exact_keys(variables.get("level_count"), expected_levels)
        and variables.get("error_messages") == expected_errors
        and variables.get("choice") in {"help", "sell"}
        and _clean_stdout(result) == "ERRORS: 2"
    )


# ---------------------------------------------------------------------------
# Tier 4 validators: functions, Caesar, Base64 and MD5
# ---------------------------------------------------------------------------


def _validate_mission_10(result: SandboxResult) -> bool:
    return (
        result.variables.get("plaintext") == "CYBER DECK SECURE"
        and result.variables.get("shift") == 3
        and _clean_stdout(result) == "CYBER DECK SECURE"
    )


def _validate_mission_11(result: SandboxResult) -> bool:
    return (
        result.variables.get("decoded") == "GREYHAT-KEY:NEON-42"
        and result.variables.get("key") == "NEON-42"
        and _clean_stdout(result) == "KEY: NEON-42"
    )


def _validate_mission_12(result: SandboxResult) -> bool:
    variables = result.variables
    return (
        variables.get("target_hash") == "c0df2d8e4db13204db830c364782eb2d"
        and variables.get("cracked_password") == "shadow-cat"
        and variables.get("choice") in {"notify", "sell"}
        and _clean_stdout(result) == "CRACKED: shadow-cat"
    )


# ---------------------------------------------------------------------------
# Tier 5 validators: threads, firewall logic and final branch
# ---------------------------------------------------------------------------


def _validate_mission_13(result: SandboxResult) -> bool:
    variables = result.variables
    attempts = variables.get("attempts")
    return (
        variables.get("password") == "spectre42"
        and type(variables.get("threads_used")) is int
        and variables.get("threads_used") == 4
        and type(attempts) is list
        and len(attempts) == 1
        and type(attempts[0]) is int
        and attempts[0] > 0
        and _clean_stdout(result) == "CRACKED: spectre42 THREADS: 4"
    )


def _validate_mission_14(result: SandboxResult) -> bool:
    expected_ports = [22, 443, 8443, 31337]
    expected_policy = {22: "blocked", 443: "allowed", 8443: "allowed", 31337: "blocked"}
    expected_receipt = send_payload("bank-gateway.local", "audit:firewall-bypass")
    variables = result.variables
    return (
        variables.get("open_ports") == expected_ports
        and _has_exact_keys(variables.get("firewall_policy"), expected_policy)
        and variables.get("bypass_port") == 443
        and variables.get("receipt") == expected_receipt
        and _clean_stdout(result) == "BYPASS: 443 ACCEPTED: True"
    )


def _validate_mission_15(result: SandboxResult) -> bool:
    variables = result.variables
    choice = variables.get("choice")
    if choice == "help":
        expected_ending = "WHITE_GHOST"
        expected_receipt = send_payload(
            "victim-node.local", "warning:3-records-exposed"
        )
    elif choice == "sell":
        expected_ending = "BLACK_GHOST"
        expected_receipt = send_payload("dark-market.local", "sale:3-records")
    else:
        return False
    return (
        variables.get("record_count") == 3
        and variables.get("ending") == expected_ending
        and variables.get("receipt") == expected_receipt
        and _clean_stdout(result) == f"ENDING: {expected_ending}"
    )


_BASE_MISSIONS: Final[tuple[Mission, ...]] = (
    Mission(
        id="m01_smart_bulb",
        title="Да будет свет",
        tier=MissionTier.SCRIPT_KIDDIE,
        description=(
            "СОСЕДСКАЯ СЕТЬ // Умная лампочка LAMP-7 каждую ночь мигает азбукой "
            "Морзе и не дает семье спать. Владелец оставил заводской пароль, а твой "
            "Cyberdeck уже получил учебный доступ к виртуальной копии устройства.\n\n"
            "Техническое задание: создай переменную device со строкой LAMP-7, "
            "brightness с целым числом 100 и choice со значением help или sell. "
            "Затем выведи одной командой строку вида: "
            "LAMP-7 brightness=100% action=help. Реального подключения к лампе нет: "
            "миссия полностью работает в офлайн-симуляторе."
        ),
        tutorial_text=(
            "Переменная — это подписанная коробка для значения. Слева пишется имя, "
            "справа после знака = — значение. Текст заключается в кавычки, а целое "
            "число пишется без них:\n\n"
            'device = "LAMP-7"\n'
            "brightness = 100\n\n"
            "print() показывает данные в терминале. Удобный способ собрать текст и "
            "значения — f-строка. Перед первой кавычкой ставится буква f, а имена "
            "переменных помещаются в фигурные скобки:\n\n"
            'print(f"{device} brightness={brightness}%")\n\n'
            "Код выполняется сверху вниз. Сначала создай все переменные, затем вызывай "
            "print(). Ошибка в регистре букв считается другим текстом."
        ),
        starter_code=(
            'device = "UNKNOWN"\n'
            "brightness = 0\n"
            'choice = "help"\n\n'
            "# Измени значения и выведи требуемую строку через f-строку.\n"
            "print(device)\n"
        ),
        hint=(
            'Установи device = "LAMP-7" и brightness = 100. Последняя строка '
            'может начинаться так: print(f"{device} brightness={brightness}% ...")'
        ),
        reward_exp=100,
        reward_btc=20,
        karma_choice=(
            "help: бесплатно исправить яркость, +5 кармы. sell: продать сведения о "
            "заводском пароле на DarkNet, -5 кармы. Валидатор принимает оба пути."
        ),
        time_limit=0,
        validator_func=_validate_mission_01,
    ),
    Mission(
        id="m02_sensor_types",
        title="Телеметрия на кухне",
        tier=MissionTier.SCRIPT_KIDDIE,
        description=(
            "ДОМАШНИЙ ХАБ // После перезапуска лампа передала дамп кухонного датчика. "
            "В нем смешаны температура, состояние сети, число повторов подключения и "
            "название комнаты. Если перепутать типы, аварийная автоматика отключит "
            "отопление.\n\n"
            "Техническое задание: сохрани 23.5 в temperature как float, True в online "
            "как bool, 3 в retries как int и kitchen в room как str. Выведи точно: "
            "TEMP=23.5 ONLINE=True RETRIES=3 ROOM=kitchen."
        ),
        tutorial_text=(
            "Python различает типы данных. int — целые числа: 3. float — дробные: "
            '23.5. str — текст в кавычках: "kitchen". bool — логика True или False, '
            "обязательно с заглавной буквы и без кавычек.\n\n"
            "Проверить тип в обычной программе можно функцией type(value), но в этой "
            'миссии достаточно правильно записать литералы. Обрати внимание: "3" — '
            'строка, а 3 — число; "True" — строка, а True — логическое значение.\n\n'
            "Несколько значений снова удобно вывести f-строкой. Python автоматически "
            "превратит числа и bool в текст внутри фигурных скобок."
        ),
        starter_code=(
            'temperature = "23.5"\n'
            'online = "True"\n'
            'retries = "3"\n'
            'room = "unknown"\n\n'
            'print(f"TEMP={temperature} ONLINE={online} RETRIES={retries} ROOM={room}")\n'
        ),
        hint=("Убери кавычки вокруг 23.5, True и 3; оставь их только вокруг kitchen."),
        reward_exp=140,
        reward_btc=30,
        karma_choice=(
            "Сюжетного выбора нет: это безопасная диагностика. Успешная передача "
            "телеметрии дает +2 кармы за помощь владельцу."
        ),
        time_limit=0,
        validator_func=_validate_mission_02,
    ),
    Mission(
        id="m03_pin_bypass",
        title="Четыре цифры до рассвета",
        tier=MissionTier.SCRIPT_KIDDIE,
        description=(
            "СЕРВИСНАЯ ПАНЕЛЬ // Хаб просит PIN. В диагностическом дампе найден "
            "stored_pin = 7319, но интерфейс все равно ожидает проверку введенного "
            "значения. Это первая развилка выполнения программы.\n\n"
            "Техническое задание: присвой entered_pin число 7319. Через if/else сравни "
            "его со stored_pin. При совпадении установи access = True и message = "
            "ACCESS GRANTED, иначе access = False и message = ACCESS DENIED. После "
            "условия выведи message."
        ),
        tutorial_text=(
            "Условие if позволяет выполнить код только при истинном выражении. Два "
            "знака == сравнивают значения; один знак = присваивает значение:\n\n"
            "if entered_pin == stored_pin:\n"
            "    access = True\n"
            "else:\n"
            "    access = False\n\n"
            "После if и else ставится двоеточие. Команды внутри ветки сдвигаются на "
            "четыре пробела. Python использует отступы вместо фигурных скобок. Код "
            "после обеих веток возвращается к левому краю и выполняется всегда."
        ),
        starter_code=(
            "stored_pin = 7319\n"
            "entered_pin = 0\n"
            "access = False\n"
            'message = "ACCESS DENIED"\n\n'
            "# Сравни entered_pin со stored_pin через if/else.\n"
            "print(message)\n"
        ),
        hint=(
            "Начни с if entered_pin == stored_pin: и в этой ветке измени access и "
            "message. Не забудь отступы."
        ),
        reward_exp=220,
        reward_btc=45,
        karma_choice=(
            "Выбора нет: доступ используется только для восстановления устройства. "
            "Миссия завершает Tier 1."
        ),
        time_limit=0,
        validator_func=_validate_mission_03,
    ),
    Mission(
        id="m04_block_list",
        title="Черный список",
        tier=MissionTier.CODE_BREAKER,
        description=(
            "ЛОГИ ШЛЮЗА // Через восстановленный хаб идут повторные попытки входа. "
            "Служба поддержки просит собрать IP только из неуспешных записей. Данные "
            "уже представлены списком словарей attempts.\n\n"
            "Техническое задание: создай пустой список blocked_ips. Циклом for перебери "
            "attempts и добавь IP записей, у которых success равен False. Сохрани длину "
            "списка в failed_count и выведи BLOCKED: 2. Порядок IP нужно сохранить."
        ),
        tutorial_text=(
            "Список хранит несколько элементов в определенном порядке:\n"
            "ports = [22, 80, 443]\n\n"
            "Цикл for берет элементы по одному:\n"
            "for port in ports:\n"
            "    print(port)\n\n"
            "Метод append(value) добавляет элемент в конец списка. Функция len(list) "
            "возвращает количество элементов. В этой миссии каждая запись — словарь, "
            'поэтому значение можно получить через entry["success"] и entry["ip"].'
        ),
        starter_code=(
            "attempts = [\n"
            '    {"ip": "10.0.0.8", "success": False},\n'
            '    {"ip": "10.0.0.2", "success": True},\n'
            '    {"ip": "10.0.0.3", "success": False},\n'
            "]\n"
            "blocked_ips = []\n\n"
            "# Перебери attempts и добавь IP неуспешных входов.\n"
            "failed_count = 0\n"
            'print(f"BLOCKED: {failed_count}")\n'
        ),
        hint=(
            'Внутри for entry in attempts: проверь if entry["success"] is False: '
            'и вызови blocked_ips.append(entry["ip"]).'
        ),
        reward_exp=300,
        reward_btc=65,
        karma_choice=(
            "Автоматическая защита жертвы: найденные адреса блокируются, +4 кармы."
        ),
        time_limit=0,
        validator_func=_validate_mission_04,
    ),
    Mission(
        id="m05_password_bruteforce",
        title="Словарная атака",
        tier=MissionTier.CODE_BREAKER,
        description=(
            "АРХИВ КАМЕРЫ // Владелец забыл пароль от собственного зашифрованного "
            "архива. Известны четыре вероятных пароля и безопасная контрольная сумма "
            "110. Нужно имитировать словарный перебор без обращения к реальным системам.\n\n"
            "Техническое задание: циклом while проверяй candidates по очереди. Для "
            "каждого вычисляй sum((i + 1) * ord(char) for i, char in "
            "enumerate(candidate)) % 997. Считай попытки. При checksum == 110 сохрани "
            "пароль и останови цикл. Выведи PASSWORD: neonfox ATTEMPTS: 4."
        ),
        tutorial_text=(
            "while повторяет блок, пока условие истинно. Индекс списка начинается с "
            "нуля:\n\n"
            "index = 0\n"
            "while index < len(candidates):\n"
            "    candidate = candidates[index]\n"
            "    index += 1\n\n"
            "Оператор += увеличивает число. break немедленно завершает ближайший цикл. "
            "enumerate(text) дает пары из позиции и символа, ord(char) превращает символ "
            "в число. Формула checksum учебная и не является настоящим хешем."
        ),
        starter_code=(
            'candidates = ["123456", "qwerty", "letmein", "neonfox"]\n'
            "target_checksum = 110\n"
            "index = 0\n"
            "attempts = 0\n"
            "password = None\n\n"
            "while index < len(candidates):\n"
            "    candidate = candidates[index]\n"
            "    checksum = 0\n"
            "    # Вычисли checksum, увеличь attempts и проверь результат.\n"
            "    index += 1\n\n"
            'print(f"PASSWORD: {password} ATTEMPTS: {attempts}")\n'
        ),
        hint=(
            "Формулу checksum можно записать одной строкой из задания. После attempts "
            "+= 1 используй if checksum == target_checksum, присвой password и break."
        ),
        reward_exp=420,
        reward_btc=90,
        karma_choice=(
            "Пароль возвращается владельцу, +5 кармы. Архив остается внутри офлайн-симуляции."
        ),
        time_limit=60,
        validator_func=_validate_mission_05,
    ),
    Mission(
        id="m06_subnet_scanner",
        title="Пять узлов в тумане",
        tier=MissionTier.CODE_BREAKER,
        description=(
            "ЛОКАЛЬНАЯ ПОДСЕТЬ // В диапазоне 10.13.37.1–10.13.37.5 появились "
            "неизвестные сервисы. Симулятор scan_ports(ip) возвращает список открытых "
            "портов без реального сетевого запроса.\n\n"
            "Техническое задание: создай список hosts через range(1, 6). Циклом for "
            "заполни scan_report, где ключ — IP, значение — результат scan_ports(). "
            "Собери vulnerable_hosts с узлами, у которых открыт порт 22. Выбери choice "
            "help или sell и выведи количество в формате VULNERABLE: 3."
        ),
        tutorial_text=(
            "range(1, 6) создает числа 1, 2, 3, 4, 5 — правая граница не входит. "
            "Список адресов удобно собрать генератором списка:\n\n"
            'hosts = [f"10.13.37.{n}" for n in range(1, 6)]\n\n'
            "Словарь создается как report = {}. Новая пара записывается так: "
            "report[host] = ports. Проверка 22 in ports возвращает True, если число "
            "есть в списке. Сначала добейся правильного отчета, затем сделай моральный выбор."
        ),
        starter_code=(
            "hosts = []\n"
            "scan_report = {}\n"
            "vulnerable_hosts = []\n"
            'choice = "help"\n\n'
            "# Создай пять IP, просканируй каждый и найди узлы с портом 22.\n"
            'print(f"VULNERABLE: {len(vulnerable_hosts)}")\n'
        ),
        hint=(
            "После создания hosts используй for host in hosts:, затем ports = "
            "scan_ports(host), scan_report[host] = ports и if 22 in ports."
        ),
        reward_exp=550,
        reward_btc=130,
        karma_choice=(
            "help: передать отчет владельцам узлов, +10 кармы. sell: продать карту "
            "подсети на DarkNet, -10 кармы."
        ),
        time_limit=75,
        validator_func=_validate_mission_06,
    ),
    Mission(
        id="m07_database_roles",
        title="Осколки базы",
        tier=MissionTier.DATA_HUNTER,
        description=(
            "УТЕЧКА CRM // На подпольном форуме появилась часть украденной базы. "
            "Чтобы предупредить организацию, нужно понять распределение ролей. Каждая "
            "запись содержит username и role.\n\n"
            "Техническое задание: сгруппируй пользователей в словаре users_by_role. "
            "Ключом должна быть роль, значением — список имен в исходном порядке. "
            "Сохрани число записей в record_count и выведи ROLES: 3 RECORDS: 4."
        ),
        tutorial_text=(
            "Словарь хранит пары ключ: значение:\n"
            'user = {"name": "mira", "role": "admin"}\n\n'
            "Метод setdefault помогает создать список для нового ключа и сразу вернуть "
            "его:\n"
            "groups.setdefault(role, []).append(username)\n\n"
            "Без setdefault можно проверить if role not in groups и сначала присвоить "
            "groups[role] = []. len(groups) считает роли, а len(records) — записи."
        ),
        starter_code=(
            "records = [\n"
            '    {"username": "mira", "role": "admin"},\n'
            '    {"username": "lev", "role": "user"},\n'
            '    {"username": "sonya", "role": "user"},\n'
            '    {"username": "service-bot", "role": "guest"},\n'
            "]\n"
            "users_by_role = {}\n"
            "record_count = 0\n\n"
            "# Сгруппируй username по role.\n"
            'print(f"ROLES: {len(users_by_role)} RECORDS: {record_count}")\n'
        ),
        hint=(
            'В цикле достань role = record["role"] и username = '
            'record["username"], затем используй setdefault.'
        ),
        reward_exp=700,
        reward_btc=170,
        karma_choice=(
            "Аналитический этап не меняет карму. Решение о судьбе данных появится в миссии 9."
        ),
        time_limit=70,
        validator_func=_validate_mission_07,
    ),
    Mission(
        id="m08_contact_cleanup",
        title="Шум в контактах",
        tier=MissionTier.DATA_HUNTER,
        description=(
            "КОНТАКТНЫЙ ДАМП // Поле email заполнено пробелами, разным регистром и "
            "мусорными значениями. Жертв нельзя предупредить, пока адреса не очищены.\n\n"
            "Техническое задание: для каждого raw_contacts вызови strip() и lower(). "
            "Оставь строки, содержащие ровно один символ @ и точку в доменной части. "
            "Сохрани валидные адреса в normalized_emails и посчитай домены в domains. "
            "Выведи VALID: 3."
        ),
        tutorial_text=(
            "Строки имеют методы. strip() убирает пробелы по краям, lower() переводит "
            'буквы в нижний регистр, count("@") считает символы. split("@") '
            "разделяет строку и возвращает список частей:\n\n"
            "email = raw.strip().lower()\n"
            'name, domain = email.split("@")\n\n'
            "Сначала проверь количество @, и только потом разделяй строку — иначе при "
            "распаковке можно получить ValueError. Счетчик доменов обновляется через "
            "domains[domain] = domains.get(domain, 0) + 1."
        ),
        starter_code=(
            "raw_contacts = [\n"
            '    "  MIRA@EXAMPLE.COM ",\n'
            '    "invalid-address",\n'
            '    "lev@greyhat.io",\n'
            '    "SONYA@EXAMPLE.COM  ",\n'
            "]\n"
            "normalized_emails = []\n"
            "domains = {}\n\n"
            "# Очисти, проверь и сгруппируй адреса.\n"
            'print(f"VALID: {len(normalized_emails)}")\n'
        ),
        hint=(
            'После email = raw.strip().lower() пропусти строку, если email.count("@") '
            '!= 1. Затем получи domain и проверь if "." in domain.'
        ),
        reward_exp=850,
        reward_btc=210,
        karma_choice=("Очистка нужна для уведомления пострадавших и дает +4 кармы."),
        time_limit=75,
        validator_func=_validate_mission_08,
    ),
    Mission(
        id="m09_log_filter",
        title="Красные строки",
        tier=MissionTier.DATA_HUNTER,
        description=(
            "ЖУРНАЛ СЕРВЕРА // Пять строк имеют формат LEVEL|service|message. Две "
            "ошибки указывают на источник утечки. Их нужно выделить, не потеряв общую "
            "статистику уровней.\n\n"
            'Техническое задание: раздели каждую строку методом split("|", 2). '
            "Посчитай INFO, WARNING и ERROR в level_count. Тексты ERROR сохрани в "
            "error_messages. Установи choice в help или sell. Выведи ERRORS: 2."
        ),
        tutorial_text=(
            "split(separator, maxsplit) делит строку не более указанного числа раз. "
            "Это важно, если сообщение само может содержать разделитель:\n\n"
            'level, service, message = line.split("|", 2)\n\n'
            'Счетчики в словаре удобно менять через get. Сравнение level == "ERROR" '
            "решает, нужно ли добавлять message в отдельный список. Для проверки префикса "
            "в других задачах пригодится startswith(), а для замены — replace()."
        ),
        starter_code=(
            "logs = [\n"
            '    "INFO|auth|session opened",\n'
            '    "ERROR|auth|invalid token",\n'
            '    "WARNING|api|rate limit",\n'
            '    "INFO|api|request complete",\n'
            '    "ERROR|db|database timeout",\n'
            "]\n"
            "level_count = {}\n"
            "error_messages = []\n"
            'choice = "help"\n\n'
            "# Раздели строки, обнови счетчики и собери ERROR.\n"
            'print(f"ERRORS: {len(error_messages)}")\n'
        ),
        hint=(
            "В цикле распакуй level, service, message. Увеличь "
            'level_count[level], а при level == "ERROR" добавь message.'
        ),
        reward_exp=1000,
        reward_btc=260,
        karma_choice=(
            "help: бесплатно отправить журнал владельцу, +15 кармы. sell: продать "
            "ошибки конкурентам, -15 кармы."
        ),
        time_limit=80,
        validator_func=_validate_mission_09,
    ),
    Mission(
        id="m10_caesar_function",
        title="Письмо Цезаря",
        tier=MissionTier.EXPLOIT_MASTER,
        description=(
            "ЗАШИФРОВАННЫЙ КАНАЛ // Перехвачено FBEHU GHFN VHFXUH. Аналитики "
            "подтвердили шифр Цезаря и сдвиг 3. Одноразовой строки уже недостаточно: "
            "нужна функция, которую можно применять к новым сообщениям.\n\n"
            "Техническое задание: создай функцию decode_message(text, shift), внутри "
            "верни decrypt_caesar(text, shift). Вызови ее для ciphertext и shift = 3, "
            "сохрани результат в plaintext и выведи CYBER DECK SECURE."
        ),
        tutorial_text=(
            "Функция — именованный блок кода с параметрами. Она объявляется через def, "
            "а return возвращает результат вызывающей строке:\n\n"
            "def add(a, b):\n"
            "    return a + b\n\n"
            "total = add(2, 3)\n\n"
            "Параметры text и shift существуют внутри функции. В песочнице уже доступен "
            "безопасный decrypt_caesar: положительный shift сдвигает буквы назад. Не "
            "печатай внутри функции, если по заданию нужен только один итоговый вывод."
        ),
        starter_code=(
            'ciphertext = "FBEHU GHFN VHFXUH"\n'
            "shift = 3\n\n"
            "def decode_message(text, amount):\n"
            "    return text\n\n"
            "plaintext = decode_message(ciphertext, shift)\n"
            "print(plaintext)\n"
        ),
        hint=(
            "Замени return text на return decrypt_caesar(text, amount). Остальной "
            "шаблон уже вызывает функцию."
        ),
        reward_exp=1200,
        reward_btc=320,
        karma_choice=(
            "Расшифрованный текст содержит настройки защиты, поэтому их передают владельцу: +5 кармы."
        ),
        time_limit=70,
        validator_func=_validate_mission_10,
    ),
    Mission(
        id="m11_base64_decoder",
        title="Не шифр, а упаковка",
        tier=MissionTier.EXPLOIT_MASTER,
        description=(
            "КОНТЕЙНЕР BASE64 // Строка R1JFWUhBVC1LRVk6TkVPTi00Mg== выглядит "
            "зашифрованной, но Base64 — лишь способ представить байты печатными "
            "символами. В разрешенном модуле base64 есть b64decode().\n\n"
            "Техническое задание: напиши функцию decode_packet(encoded). Преобразуй "
            'encoded в bytes через encode("ascii"), декодируй base64.b64decode(), '
            'затем преврати bytes в строку через decode("utf-8"). Сохрани полный '
            "текст в decoded, часть после двоеточия в key и выведи KEY: NEON-42."
        ),
        tutorial_text=(
            "Компьютер хранит данные как байты. Метод строки encode() создает bytes, а "
            "метод bytes.decode() снова создает str:\n\n"
            'raw_bytes = text.encode("utf-8")\n'
            'text_again = raw_bytes.decode("utf-8")\n\n'
            "После import base64 декодирование выглядит так: "
            "base64.b64decode(encoded_bytes). Результат еще является bytes. Чтобы взять "
            'часть после KEY:, используй decoded.split(":", 1)[1]. Base64 не защищает '
            "секрет и никогда не заменяет шифрование."
        ),
        starter_code=(
            "import base64\n\n"
            'packet = "R1JFWUhBVC1LRVk6TkVPTi00Mg=="\n\n'
            "def decode_packet(encoded):\n"
            '    encoded_bytes = encoded.encode("ascii")\n'
            '    return encoded_bytes.decode("ascii")\n\n'
            "decoded = decode_packet(packet)\n"
            'key = ""\n'
            'print(f"KEY: {key}")\n'
        ),
        hint=(
            "В функции сначала сделай decoded_bytes = base64.b64decode(encoded_bytes), "
            'затем return decoded_bytes.decode("utf-8"). key находится после двоеточия.'
        ),
        reward_exp=1450,
        reward_btc=390,
        karma_choice=("Контейнер исследуется локально; карма не меняется."),
        time_limit=80,
        validator_func=_validate_mission_11,
    ),
    Mission(
        id="m12_md5_cracker",
        title="Трещина в MD5",
        tier=MissionTier.EXPLOIT_MASTER,
        description=(
            "СТАРЫЙ ФОРУМ // В утечке найден MD5 c0df2d8e4db13204db830c364782eb2d. "
            "MD5 необратим, но слабый пароль можно найти сравнением хешей кандидатов. "
            "Все данные вымышлены и обрабатываются офлайн.\n\n"
            "Техническое задание: создай функцию crack_md5(target, candidates). Для "
            'каждого candidate вычисли hashlib.md5(candidate.encode("utf-8")).hexdigest(). '
            "Верни совпавший пароль или None. Сохрани результат в cracked_password, "
            "установи choice в notify или sell и выведи CRACKED: shadow-cat."
        ),
        tutorial_text=(
            "Хеш-функция превращает данные в строку фиксированной длины. Проверка "
            "пароля хеширует кандидата тем же алгоритмом и сравнивает строки:\n\n"
            'digest = hashlib.md5(candidate.encode("utf-8")).hexdigest()\n'
            "if digest == target:\n"
            "    return candidate\n\n"
            "return None размещают после цикла: это результат, когда ни один кандидат "
            "не подошел. MD5 устарел для хранения паролей; реальные системы используют "
            "Argon2, bcrypt или scrypt с солью."
        ),
        starter_code=(
            "import hashlib\n\n"
            'target_hash = "c0df2d8e4db13204db830c364782eb2d"\n'
            'candidates = ["admin", "winter", "shadow-cat", "neonfox"]\n'
            'choice = "notify"\n\n'
            "def crack_md5(target, words):\n"
            "    for candidate in words:\n"
            '        digest = ""\n'
            "        if digest == target:\n"
            "            return candidate\n"
            "    return None\n\n"
            "cracked_password = crack_md5(target_hash, candidates)\n"
            'print(f"CRACKED: {cracked_password}")\n'
        ),
        hint=(
            'Замени digest = "" на hashlib.md5(candidate.encode("utf-8")).hexdigest().'
        ),
        reward_exp=1750,
        reward_btc=480,
        karma_choice=(
            "notify: предупредить владельца форума, +20 кармы. sell: продать пароль, "
            "-20 кармы."
        ),
        time_limit=90,
        validator_func=_validate_mission_12,
    ),
    Mission(
        id="m13_threaded_bruteforce",
        title="Четыре охотника",
        tier=MissionTier.NETWORK_GHOST,
        description=(
            "РАСПРЕДЕЛЕННЫЙ СЕЙФ // Учебный набор содержит 201 кандидат и MD5 пароля "
            "spectre42. Один цикл справится, но задача Tier 5 — разделить список между "
            "четырьмя потоками. Потоки существуют только внутри ограниченного процесса "
            "песочницы.\n\n"
            "Техническое задание: создай четыре threading.Thread. Каждый получает срез "
            "candidates[worker_id::4], хеширует слова и при совпадении записывает пароль "
            "в общий список found. Изменяй attempts под Lock. Запусти и присоедини все "
            "потоки. Установи threads_used = 4, password и выведи "
            "CRACKED: spectre42 THREADS: 4."
        ),
        tutorial_text=(
            "Поток выполняет функцию параллельно с другими потоками. Создание и ожидание:\n\n"
            "thread = threading.Thread(target=worker, args=(chunk,))\n"
            "thread.start()\n"
            "thread.join()\n\n"
            "Общие изменяемые данные могут привести к гонке. Lock гарантирует, что "
            "счетчик меняет только один поток за раз:\n"
            "with lock:\n"
            "    attempts[0] += 1\n\n"
            "Список attempts используется вместо int, потому что его содержимое можно "
            "менять из функции. Потоки полезны для ожидания I/O; для тяжелых вычислений "
            "CPython часто требует процессы."
        ),
        starter_code=(
            "import hashlib\n"
            "import threading\n\n"
            'target_hash = "69b46cdab079035c72b25d448bc0ffdd"\n'
            'candidates = [f"ghost{n:03d}" for n in range(200)] + ["spectre42"]\n'
            "found = []\n"
            "attempts = [0]\n"
            "lock = threading.Lock()\n\n"
            "def worker(chunk):\n"
            "    for candidate in chunk:\n"
            '        digest = hashlib.md5(candidate.encode("utf-8")).hexdigest()\n'
            "        with lock:\n"
            "            attempts[0] += 1\n"
            "        if digest == target_hash:\n"
            "            found.append(candidate)\n"
            "            return\n\n"
            "threads = []\n"
            "# Создай четыре потока со срезами candidates[worker_id::4].\n"
            "# Затем start() каждый поток и отдельным циклом вызови join().\n\n"
            "threads_used = len(threads)\n"
            "password = found[0] if found else None\n"
            'print(f"CRACKED: {password} THREADS: {threads_used}")\n'
        ),
        hint=(
            "В цикле for worker_id in range(4) создай chunk, затем Thread(target=worker, "
            "args=(chunk,)) и append. После этого нужны два отдельных цикла: start и join."
        ),
        reward_exp=2200,
        reward_btc=650,
        karma_choice=(
            "Лабораторная атака не меняет карму. Лимит 20 секунд требует завершить все потоки."
        ),
        time_limit=20,
        validator_func=_validate_mission_13,
    ),
    Mission(
        id="m14_bank_firewall",
        title="Стеклянный файрвол",
        tier=MissionTier.NETWORK_GHOST,
        description=(
            "БАНКОВСКИЙ АУДИТ // Банк нанял тебя проверить виртуальный шлюз "
            "bank-gateway.local. scan_ports() показывает 22, 443, 8443 и забытый 31337. "
            "Политика должна разрешать только web-порты, а тестовый payload обязан уйти "
            "через 443.\n\n"
            "Техническое задание: напиши функцию build_policy(ports), возвращающую "
            "словарь port -> allowed/blocked. Разреши 443 и 8443, остальные заблокируй. "
            "Выбери минимальный разрешенный bypass_port, отправь "
            "audit:firewall-bypass через send_payload(), сохрани receipt и выведи "
            "BYPASS: 443 ACCEPTED: True."
        ),
        tutorial_text=(
            "Комплексная задача объединяет функцию, цикл, словарь, условие и API. "
            "Функция может построить и вернуть целую структуру:\n\n"
            "def build_policy(ports):\n"
            "    policy = {}\n"
            "    for port in ports:\n"
            '        policy[port] = "allowed" if port in (443, 8443) else "blocked"\n'
            "    return policy\n\n"
            "Выражение value_if_true if condition else value_if_false называется "
            "тернарным. Разрешенные порты можно отфильтровать и передать в min(). "
            "send_payload — офлайн-симулятор и не отправляет сетевые пакеты."
        ),
        starter_code=(
            'target = "bank-gateway.local"\n'
            "open_ports = scan_ports(target)\n\n"
            "def build_policy(ports):\n"
            "    policy = {}\n"
            "    # Для каждого порта запиши allowed или blocked.\n"
            "    return policy\n\n"
            "firewall_policy = build_policy(open_ports)\n"
            "bypass_port = None\n"
            "receipt = {}\n"
            "# Найди разрешенный порт и вызови send_payload().\n"
            "print(f\"BYPASS: {bypass_port} ACCEPTED: {receipt.get('accepted')}\")\n"
        ),
        hint=(
            "После build_policy собери allowed_ports из элементов со status == "
            '"allowed", возьми min(). receipt = send_payload(target, '
            '"audit:firewall-bypass").'
        ),
        reward_exp=2800,
        reward_btc=850,
        karma_choice=(
            "Это согласованный аудит банка. Корректный отчет закрывает 22 и 31337 и дает +15 кармы."
        ),
        time_limit=25,
        validator_func=_validate_mission_14,
    ),
    Mission(
        id="m15_final_choice",
        title="Исчезнуть или остаться человеком",
        tier=MissionTier.NETWORK_GHOST,
        description=(
            "ФИНАЛ // За банковским шлюзом обнаружены три записи о жертвах утечки. "
            "DarkNet предлагает 5000 BTC за архив. victim-node.local ждет предупреждение. "
            "Никто не выберет за тебя.\n\n"
            "Техническое задание: создай функцию resolve_final(choice, records). Для "
            "help отправь на victim-node.local строку warning:3-records-exposed и верни "
            "WHITE_GHOST. Для sell отправь на dark-market.local строку sale:3-records "
            "и верни BLACK_GHOST. Функция должна вернуть пару ending, receipt. Сохрани "
            "record_count, вызови функцию и выведи ENDING: выбранный_финал."
        ),
        tutorial_text=(
            "Финальная программа объединяет изученные темы. len(records) дает количество. "
            "Функция может вернуть два значения через запятую, а вызывающий код сразу их "
            "распакует:\n\n"
            "ending, receipt = resolve_final(choice, records)\n\n"
            "В каждой ветке if можно подготовить свой target и payload. f-строка "
            "подставит record_count. После send_payload верни строку финала и receipt. "
            "Валидатор принимает оба честно реализованных пути; награда и карма должны "
            "обрабатываться игровым состоянием после проверки."
        ),
        starter_code=(
            "records = [\n"
            '    {"victim": "Mira", "leak": "email"},\n'
            '    {"victim": "Lev", "leak": "token"},\n'
            '    {"victim": "Sonya", "leak": "wallet"},\n'
            "]\n"
            "record_count = len(records)\n"
            'choice = "undecided"\n\n'
            "def resolve_final(action, stolen_records):\n"
            "    count = len(stolen_records)\n"
            '    if action == "help":\n'
            '        target = "victim-node.local"\n'
            '        payload = f"warning:{count}-records-exposed"\n'
            '        ending_name = "WHITE_GHOST"\n'
            "    else:\n"
            '        target = "dark-market.local"\n'
            '        payload = f"sale:{count}-records"\n'
            '        ending_name = "BLACK_GHOST"\n'
            "    delivery = send_payload(target, payload)\n"
            "    return ending_name, delivery\n\n"
            "ending, receipt = resolve_final(choice, records)\n"
            'print(f"ENDING: {ending}")\n'
        ),
        hint=(
            'Шаблон уже содержит всю структуру. Выбери choice = "help" или '
            'choice = "sell", проверь payload и запусти код.'
        ),
        reward_exp=5000,
        reward_btc=1500,
        karma_choice=(
            "help: предупредить трех жертв, +50 кармы и финал WHITE_GHOST. sell: "
            "продать архив, -50 кармы, крупный теневой бонус и финал BLACK_GHOST."
        ),
        time_limit=30,
        validator_func=_validate_mission_15,
    ),
)

_SENIOR_TRAPS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "m01_smart_bulb": (
            "В дампе есть ложное устройство LAMP-0. Не используй decoy_device в "
            "итоговой строке: реальные параметры принадлежат только LAMP-7."
        ),
        "m02_sensor_types": (
            "Строки '23.5', 'True' и '3' выглядят правильно при печати, но имеют "
            "неверные типы. Сохрани точные float, bool и int без преобразования в str."
        ),
        "m03_pin_bypass": (
            "Условие if entered_pin: является обманкой: любое ненулевое число даст "
            "True. Сравни PIN со stored_pin оператором == и заполни обе ветки."
        ),
        "m04_block_list": (
            "Одинаковые IP могут появляться повторно в других наборах. Здесь сохраняй "
            "исходный порядок и не изменяй список attempts во время обхода."
        ),
        "m05_password_bruteforce": (
            "Не запускай второй цикл для каждого кандидата вручную. Используй один "
            "while и генератор в sum; явная вложенная пара циклов считается O(n²)."
        ),
        "m06_subnet_scanner": (
            "Не сканируй один host повторно при проверке порта 22. Сохрани ports в "
            "scan_report и используй тот же список для определения уязвимости."
        ),
        "m07_database_roles": (
            "Роли идут не по алфавиту. Не сортируй records и не делай отдельный проход "
            "для каждой роли: решение должно группировать данные за один проход O(n)."
        ),
        "m08_contact_cleanup": (
            "Строка invalid-address не содержит @. Сначала проверь count('@'), иначе "
            "распаковка split завершится ошибкой. Повторные полные проходы запрещены."
        ),
        "m09_log_filter": (
            "Сообщение лога потенциально содержит символ |. Используй split('|', 2), "
            "иначе скрытая строка разобьется больше чем на три части."
        ),
        "m10_caesar_function": (
            "Параметр функции называется amount, а глобальная переменная — shift. "
            "Не подменяй параметр глобальным значением: функция должна быть повторяемой."
        ),
        "m11_base64_decoder": (
            "Base64 возвращает bytes. Вызов str(decoded_bytes) создаст текст вида "
            "b'...'; требуется настоящее decode('utf-8') и один split по двоеточию."
        ),
        "m12_md5_cracker": (
            "target_hash уже является hex-строкой. Не хешируй его повторно и не "
            "сравнивай bytes с str. Заверши поиск сразу после первого совпадения."
        ),
        "m13_threaded_bruteforce": (
            "Создание нового потока для каждого из 201 кандидата является ловушкой. "
            "Нужно ровно четыре потока и четыре непересекающихся среза списка."
        ),
        "m14_bank_firewall": (
            "Порт 31337 намеренно выглядит привлекательным, но должен быть blocked. "
            "Политику построй за один проход, а bypass выбери только из allowed."
        ),
        "m15_final_choice": (
            "Ветка else не должна молча принимать произвольный action. Секретная цель: "
            "сохрани O(n) обработку records и не отправляй payload больше одного раза."
        ),
    }
)

_SKILL_TIMER_MULTIPLIERS: Final[Mapping[str, float]] = MappingProxyType(
    {
        "zero": 3.0,
        "beginner": 2.0,
        "practice": 1.0,
        "advanced": 0.7,
        "senior": 0.4,
    }
)

_SENIOR_DECOYS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "m01_smart_bulb": 'decoy_device = "LAMP-0"\n',
        "m02_sensor_types": 'decoy_temperature = "23.5"\n',
        "m03_pin_bypass": "decoy_pin = 1111\n",
        "m04_block_list": 'decoy_ip = "10.0.0.13"\n',
        "m05_password_bruteforce": 'decoy_password = "admin"\n',
        "m06_subnet_scanner": 'decoy_host = "127.0.0.1"\n',
        "m07_database_roles": 'decoy_role = {"name": "root", "access": True}\n',
        "m08_contact_cleanup": 'decoy_contact = "root@localhost"\n',
        "m09_log_filter": 'decoy_level = "DEBUG"\n',
        "m10_caesar_function": "decoy_shift = 13\n",
        "m11_base64_decoder": 'decoy_encoding = "ascii"\n',
        "m12_md5_cracker": 'decoy_hash = "d41d8cd98f00b204e9800998ecf8427e"\n',
        "m13_threaded_bruteforce": "decoy_workers = 201\n",
        "m14_bank_firewall": "decoy_port = 31337\n",
        "m15_final_choice": 'decoy_action = "leak"\n',
    }
)

_BEGINNER_STARTER_OVERRIDES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "m01_smart_bulb": (
            'device = "LAMP-7"  # Имя устройства уже найдено.\n'
            "brightness = 0  # Замени ноль на число 100 без кавычек.\n"
            'choice = "help"  # Можно заменить на "sell".\n\n'
            "# Собери вывод: LAMP-7 brightness=100% action=help\n"
            'print(f"{device} brightness={brightness}% action={choice}")\n'
        ),
        "m02_sensor_types": (
            "temperature = 23.5  # float\n"
            "online = True  # bool\n"
            "retries = 3  # int\n"
            'room = "unknown"  # Замени на kitchen.\n\n'
            'print(f"TEMP={temperature} ONLINE={online} RETRIES={retries} ROOM={room}")\n'
        ),
        "m03_pin_bypass": (
            "stored_pin = 7319\n"
            "entered_pin = 0  # Впиши найденный PIN.\n"
            "if entered_pin == stored_pin:\n"
            "    access = True\n"
            '    message = "ACCESS GRANTED"\n'
            "else:\n"
            "    access = False\n"
            '    message = "ACCESS DENIED"\n'
            "print(message)\n"
        ),
    }
)


def _guidance_for_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "# Пустая строка отделяет этапы решения."
    if stripped.startswith("#"):
        return line
    if stripped.startswith("import ") or stripped.startswith("from "):
        note = "подключаем безопасный модуль"
    elif stripped.startswith("def "):
        note = "объявляем функцию"
    elif stripped.startswith(("for ", "while ")):
        note = "начинаем цикл"
    elif stripped.startswith(("if ", "elif ", "else:")):
        note = "проверяем условие"
    elif stripped.startswith("return"):
        note = "возвращаем результат"
    elif "print(" in stripped:
        note = "выводим результат в терминал"
    elif "=" in stripped:
        note = "сохраняем значение в переменную"
    elif stripped[0] in "]})":
        note = "закрываем структуру данных"
    else:
        note = "выполняем следующий шаг"
    return f"{line}  # {note}"


def _add_line_guidance(starter_code: str) -> str:
    return (
        "\n".join(_guidance_for_line(line) for line in starter_code.splitlines()) + "\n"
    )


def _strip_instruction_comments(starter_code: str) -> str:
    """Удаляет полноценные и inline-комментарии, не затрагивая ``#`` в строках."""

    source = io.StringIO(starter_code)
    tokens = (
        token_info
        for token_info in tokenize.generate_tokens(source.readline)
        if token_info.type != tokenize.COMMENT
    )
    without_comments = tokenize.untokenize(tokens)
    lines = [line.rstrip() for line in without_comments.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def _short_tutorial(tutorial_text: str) -> str:
    paragraphs = [part.strip() for part in tutorial_text.split("\n\n") if part.strip()]
    return "\n\n".join(paragraphs[:2])


def adapt_mission(
    mission: Mission,
    skill_level: str,
    *,
    timer_multiplier: float | None = None,
) -> Mission:
    """Возвращает неизменяемую копию миссии для уровня игрока."""

    if skill_level not in SKILL_LEVELS:
        allowed = ", ".join(SKILL_LEVELS)
        raise ValueError(f"Неизвестный skill_level; доступны: {allowed}")
    multiplier = (
        _SKILL_TIMER_MULTIPLIERS[skill_level]
        if timer_multiplier is None
        else float(timer_multiplier)
    )
    if multiplier <= 0:
        raise ValueError("timer_multiplier должен быть положительным")
    adapted_time = (
        0
        if mission.time_limit == 0
        else max(8, int(round(mission.time_limit * multiplier)))
    )

    tutorial = mission.tutorial_text
    starter = mission.starter_code
    description = mission.description
    if skill_level == "zero":
        tutorial = (
            "РЕЖИМ ПЕРВОГО КОДА. Каждая строка стартового кода снабжена "
            "комментарием. Читай программу сверху вниз: справа от символа # написано, "
            "зачем нужен шаг. Ошибки безопасны и остаются внутри Sandbox.\n\n"
            "ПОШАГОВЫЙ ПЛАН:\n"
            "1. Прочитай условие и найди имена требуемых переменных.\n"
            "2. Замени значения-заглушки в стартовом коде.\n"
            "3. Нажми F5 и сравни вывод терминала с форматом в задании.\n"
            "4. Если появилась ошибка, исправь указанную строку и запусти снова.\n"
            "5. Не удаляй этические переменные help/sell: они меняют карму.\n\n"
            f"{mission.tutorial_text}"
        )
        starter = _add_line_guidance(mission.starter_code)
    elif skill_level == "beginner":
        tutorial = mission.tutorial_text
        starter = _BEGINNER_STARTER_OVERRIDES.get(mission.id, mission.starter_code)
    elif skill_level == "practice":
        tutorial = _short_tutorial(mission.tutorial_text)
    elif skill_level == "advanced":
        tutorial = ""
        starter = _strip_instruction_comments(mission.starter_code)
        if mission.id == "m14_bank_firewall":
            description = (
                f"{mission.description}\n\nADAPTIVE FIREWALL // каждая ошибка ускоряет Trace "
                "Meter; повторяющиеся попытки получают повышенный штраф."
            )
    else:
        tutorial = ""
        starter = _SENIOR_DECOYS[mission.id] + _strip_instruction_comments(
            mission.starter_code
        )
        description = (
            f"{mission.description}\n\nSENIOR PROTOCOL // {mission.senior_trap}"
        )

    return replace(
        mission,
        description=description,
        tutorial_text=tutorial,
        starter_code=starter,
        time_limit=adapted_time,
    )


def adapt_missions(
    skill_level: str,
    *,
    timer_multiplier: float | None = None,
) -> tuple[Mission, ...]:
    return tuple(
        adapt_mission(
            mission,
            skill_level,
            timer_multiplier=timer_multiplier,
        )
        for mission in MISSIONS
    )


class _LoopComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.depth = 0
        self.maximum_depth = 0
        self.multi_generator_comprehension = False

    def _visit_loop(self, node: ast.AST) -> None:
        self.depth += 1
        self.maximum_depth = max(self.maximum_depth, self.depth)
        self.generic_visit(node)
        self.depth -= 1

    def visit_For(self, node: ast.For) -> None:
        self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_loop(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_loop(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        if len(node.generators) > 1:
            self.multi_generator_comprehension = True
        self.generic_visit(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        if len(node.generators) > 1:
            self.multi_generator_comprehension = True
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        if len(node.generators) > 1:
            self.multi_generator_comprehension = True
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        if len(node.generators) > 1:
            self.multi_generator_comprehension = True
        self.generic_visit(node)


def validate_senior_efficiency(mission_id: str, source_code: str) -> bool:
    """Отклоняет очевидный O(n²), когда миссия решается за один проход."""

    if mission_id not in MISSION_BY_ID or not isinstance(source_code, str):
        return False
    try:
        tree = ast.parse(source_code, mode="exec")
    except SyntaxError:
        return False
    visitor = _LoopComplexityVisitor()
    visitor.visit(tree)
    return visitor.maximum_depth <= 1 and not visitor.multi_generator_comprehension


MISSIONS: Final[tuple[Mission, ...]] = tuple(
    replace(mission, senior_trap=_SENIOR_TRAPS[mission.id])
    for mission in _BASE_MISSIONS
)

MISSION_BY_ID: Final[Mapping[str, Mission]] = MappingProxyType(
    {mission.id: mission for mission in MISSIONS}
)
MISSIONS_BY_TIER: Final[Mapping[MissionTier, tuple[Mission, ...]]] = MappingProxyType(
    {
        tier: tuple(mission for mission in MISSIONS if mission.tier is tier)
        for tier in MissionTier
    }
)


def get_mission(mission_id: str) -> Mission:
    """Возвращает миссию по id с понятной ошибкой для неизвестного значения."""

    try:
        return MISSION_BY_ID[mission_id]
    except KeyError as exc:
        raise KeyError(f"Неизвестная миссия: {mission_id}") from exc


def get_missions_for_tier(tier: MissionTier | int) -> tuple[Mission, ...]:
    """Возвращает три миссии выбранного уровня сложности."""

    try:
        normalized_tier = MissionTier(tier)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Неизвестный tier: {tier!r}") from exc
    return MISSIONS_BY_TIER[normalized_tier]


def validate_mission(mission_id: str, result: SandboxResult) -> bool:
    """Проверяет результат запуска для указанной миссии."""

    return get_mission(mission_id).validate(result)


__all__ = [
    "MISSION_BY_ID",
    "MISSIONS",
    "MISSIONS_BY_TIER",
    "Mission",
    "MissionTier",
    "MissionValidator",
    "TIER_NAMES",
    "adapt_mission",
    "adapt_missions",
    "get_mission",
    "get_missions_for_tier",
    "validate_mission",
    "validate_senior_efficiency",
]
