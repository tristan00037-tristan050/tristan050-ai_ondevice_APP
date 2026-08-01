from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any


MAX_JSON_BYTES = 64 * 1024
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 2048
MAX_STRING_CHARS = 8192
MAX_INTEGER_DIGITS = 16


class StrictJsonError(ValueError):
    """Stable, content-free failure for trusted persisted JSON."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise StrictJsonError("JSON_DUPLICATE_KEY")
        value[key] = item
    return value


def _reject_non_finite(_value: str) -> None:
    raise StrictJsonError("JSON_NON_FINITE_FORBIDDEN")


def _parse_int(value: str) -> int:
    digits = value.removeprefix("-")
    if len(digits) > MAX_INTEGER_DIGITS:
        raise StrictJsonError("JSON_INTEGER_TOO_LARGE")
    return int(value)


def _parse_float(value: str) -> Decimal:
    return Decimal(value)


def _validate_tree(root: object, *, allow_float: bool) -> None:
    nodes = 0
    stack: list[tuple[object, int]] = [(root, 1)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise StrictJsonError("JSON_TOO_COMPLEX")
        if depth > MAX_JSON_DEPTH:
            raise StrictJsonError("JSON_TOO_DEEP")
        if isinstance(value, str):
            if len(value) > MAX_STRING_CHARS:
                raise StrictJsonError("JSON_STRING_TOO_LONG")
            if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
                raise StrictJsonError("JSON_UNPAIRED_SURROGATE")
        elif type(value) is dict:
            for key, item in value.items():
                stack.append((key, depth + 1))
                stack.append((item, depth + 1))
        elif type(value) is list:
            stack.extend((item, depth + 1) for item in value)
        elif type(value) is Decimal:
            if not allow_float or not value.is_finite():
                raise StrictJsonError("JSON_FLOAT_FORBIDDEN")
        elif type(value) is int:
            if len(str(abs(value))) > MAX_INTEGER_DIGITS:
                raise StrictJsonError("JSON_INTEGER_TOO_LARGE")
        elif value is not None and type(value) is not bool:
            raise StrictJsonError("JSON_VALUE_TYPE_INVALID")


def load_strict_bytes(
    raw: bytes,
    *,
    max_bytes: int = MAX_JSON_BYTES,
    allow_float: bool = False,
) -> dict[str, Any]:
    if type(raw) is not bytes:
        raise StrictJsonError("JSON_BYTES_REQUIRED")
    if len(raw) > max_bytes:
        raise StrictJsonError("JSON_TOO_LARGE")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise StrictJsonError("JSON_UTF8_INVALID") from exc
    if text.startswith("\ufeff"):
        raise StrictJsonError("JSON_BOM_FORBIDDEN")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_non_finite,
            parse_float=_parse_float,
            parse_int=_parse_int,
        )
    except StrictJsonError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise StrictJsonError("JSON_SYNTAX_INVALID") from exc
    if type(value) is not dict:
        raise StrictJsonError("JSON_ROOT_NOT_OBJECT")
    _validate_tree(value, allow_float=allow_float)
    if allow_float:
        value = _decimal_to_float(value)
    return value


def _decimal_to_float(value: Any) -> Any:
    if type(value) is Decimal:
        converted = float(value)
        if not math.isfinite(converted):
            raise StrictJsonError("JSON_NON_FINITE_FORBIDDEN")
        return converted
    if type(value) is list:
        return [_decimal_to_float(item) for item in value]
    if type(value) is dict:
        return {key: _decimal_to_float(item) for key, item in value.items()}
    return value


def dump_canonical_bytes(value: dict[str, Any]) -> bytes:
    if type(value) is not dict:
        raise StrictJsonError("JSON_ROOT_NOT_OBJECT")
    _validate_tree(value, allow_float=False)
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StrictJsonError("JSON_SERIALIZATION_INVALID") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise StrictJsonError("JSON_TOO_LARGE")
    return raw
