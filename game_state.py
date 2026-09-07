"""Состояние игрока и безопасное JSON-сохранение прогресса."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Mapping


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


SKILL_LEVELS: tuple[str, ...] = (
    "zero",
    "beginner",
    "practice",
    "advanced",
    "senior",
)

_SKILL_TIMER_MULTIPLIERS: dict[str, float] = {
    "zero": 3.0,
    "beginner": 2.0,
    "practice": 1.0,
    "advanced": 0.7,
    "senior": 0.4,
}

_SKILL_HINT_COSTS: dict[str, int] = {
    "zero": 0,
    "beginner": 0,
    "practice": 10,
    "advanced": 30,
    "senior": 0,
}

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
    skill_level: str = "practice"

    SAVE_VERSION: ClassVar[int] = 1
    MIN_KARMA: ClassVar[int] = -100
    MAX_KARMA: ClassVar[int] = 100

    def __post_init__(self) -> None:
        self.bitcoins = _require_non_negative_int(self.bitcoins, "bitcoins")
        self.exp = _require_non_negative_int(self.exp, "exp")
        if isinstance(self.karma, bool) or not isinstance(self.karma, int):
            raise TypeError("karma должна быть целым числом")
        self.karma = max(self.MIN_KARMA, min(self.MAX_KARMA, self.karma))
        if not isinstance(self.skill_level, str):
            raise TypeError("skill_level должен быть строкой")
        if self.skill_level not in SKILL_LEVELS:
            allowed = ", ".join(SKILL_LEVELS)
            raise ValueError(f"skill_level должен быть одним из: {allowed}")

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

    def get_timer_multiplier(self) -> float:
        """Возвращает множитель mission timer для выбранного уровня навыка."""

        return _SKILL_TIMER_MULTIPLIERS[self.skill_level]

    def get_hint_cost(self) -> int:
        """Возвращает цену одной подсказки; Senior-подсказки отключает UI."""

        return _SKILL_HINT_COSTS[self.skill_level]

    def should_show_tutorial(self) -> bool:
        """Продвинутый и Senior начинают без встроенного учебника."""

        return self.skill_level in {"zero", "beginner", "practice"}

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
            "skill_level": self.skill_level,
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
                skill_level=data.get("skill_level", "practice"),
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
    "SKILL_LEVELS",
]
