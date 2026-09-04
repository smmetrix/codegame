"""Изолированное выполнение учебного Python-кода.

Код сначала проверяется через AST, затем выполняется в отдельном процессе без
файловых, сетевых и процессных builtins. Процесс ограничен по времени, памяти
и размеру вывода. API этого модуля выполняет только детерминированную симуляцию
сети: реальных сетевых запросов из песочницы нет.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import hashlib
import io
import ipaddress
import math
import multiprocessing
import os
import re
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field, replace
from multiprocessing.connection import Connection
from types import MappingProxyType
from typing import Any, Final, Mapping


DEFAULT_TIMEOUT_SECONDS: Final[float] = 3.0
DEFAULT_MAX_OUTPUT_CHARS: Final[int] = 50_000
DEFAULT_MAX_MEMORY_MB: Final[int] = 256
DEFAULT_MAX_AST_NODES: Final[int] = 10_000
MAX_SOURCE_CHARS: Final[int] = 100_000
MAX_SERIALIZED_ITEMS: Final[int] = 500
MAX_VALUE_DEPTH: Final[int] = 8

_ALLOWED_MODULES: Final[frozenset[str]] = frozenset(
    {
        "base64",
        "hashlib",
        "json",
        "math",
        "re",
        "statistics",
        "string",
        "threading",
    }
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
            "bank-gateway.local": (22, 443, 8443, 31337),
            "cyberdeck.local": (22, 80, 443, 31337),
            "vault.greyhat": (21, 22, 443, 3306),
            "victim-node.local": (22, 443, 5432),
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

    import base64
    import hashlib
    import json
    import math as math_module
    import re as re_module
    import statistics
    import string
    import threading

    selected_names: Mapping[str, tuple[str, ...]] = {
        "base64": (
            "b64decode",
            "b64encode",
            "standard_b64decode",
            "standard_b64encode",
            "urlsafe_b64decode",
            "urlsafe_b64encode",
        ),
        "hashlib": (
            "md5",
            "sha1",
            "sha224",
            "sha256",
            "sha384",
            "sha512",
        ),
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
        "threading": (
            "Barrier",
            "BoundedSemaphore",
            "Event",
            "Lock",
            "RLock",
            "Semaphore",
            "Thread",
        ),
    }
    real_modules: Mapping[str, Any] = {
        "base64": base64,
        "hashlib": hashlib,
        "json": json,
        "re": re_module,
        "statistics": statistics,
        "string": string,
        "threading": threading,
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
