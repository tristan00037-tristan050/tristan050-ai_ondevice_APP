from __future__ import annotations

import json
from typing import Any


MAX_JSON_BYTES = 64 * 1024
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 2048
MAX_STRING_CHARS = 8192
MAX_INTEGER_DIGITS = 20


class StrictJsonError(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_non_finite(_value: str) -> None:
    raise StrictJsonError("JSON_NON_FINITE_FORBIDDEN")


def _reject_float(_value: str) -> None:
    raise StrictJsonError("JSON_FLOAT_FORBIDDEN")


def _parse_bounded_int(value: str) -> int:
    digits = value.removeprefix("-")
    if len(digits) > MAX_INTEGER_DIGITS:
        raise StrictJsonError("JSON_INTEGER_TOO_LARGE")
    return int(value)


def _validate_string(value: str) -> None:
    if len(value) > MAX_STRING_CHARS:
        raise StrictJsonError("JSON_STRING_TOO_LONG")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise StrictJsonError("JSON_UNPAIRED_SURROGATE")


def _enforce_complexity(root: object) -> None:
    nodes = 0
    stack: list[tuple[object, int]] = [(root, 1)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise StrictJsonError("JSON_TOO_COMPLEX")
        if depth > MAX_JSON_DEPTH:
            raise StrictJsonError("JSON_TOO_DEEP")
        if isinstance(value, dict):
            for key, child in value.items():
                _validate_string(key)
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            _validate_string(value)
        elif value is not None and type(value) not in {bool, int}:
            raise StrictJsonError("JSON_VALUE_TYPE_FORBIDDEN")


def load_strict_bytes(
    raw: bytes,
    *,
    max_bytes: int = MAX_JSON_BYTES,
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
            parse_float=_reject_float,
            parse_int=_parse_bounded_int,
        )
    except StrictJsonError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise StrictJsonError("JSON_INVALID") from exc
    if type(value) is not dict:
        raise StrictJsonError("JSON_ROOT_NOT_OBJECT")
    _enforce_complexity(value)
    return value


def canonical_json_bytes(value: dict[str, Any]) -> bytes:
    if type(value) is not dict:
        raise StrictJsonError("JSON_ROOT_NOT_OBJECT")
    _enforce_complexity(value)
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise StrictJsonError("JSON_CANONICALIZATION_FAILED") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise StrictJsonError("JSON_TOO_LARGE")
    if load_strict_bytes(raw) != value:
        raise StrictJsonError("JSON_CANONICALIZATION_MISMATCH")
    return raw
