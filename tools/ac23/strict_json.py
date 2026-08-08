#!/usr/bin/env python3
"""Strict JSON boundary primitives for AC-23 source-side tools.

The packaged verifier intentionally carries an independent implementation.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class StrictJsonError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise StrictJsonError(f"non-finite number: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError("duplicate key")
        result[key] = value
    return result


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def strict_json_bytes(
    payload: bytes,
    *,
    max_bytes: int,
    require_canonical: bool = False,
) -> Any:
    if type(payload) is not bytes or not payload or len(payload) > max_bytes:
        raise StrictJsonError("JSON size")
    if payload.startswith(b"\xef\xbb\xbf"):
        raise StrictJsonError("JSON BOM")
    try:
        text = payload.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, StrictJsonError) as error:
        raise StrictJsonError("invalid JSON") from error
    if require_canonical and canonical_json_bytes(value) != payload:
        raise StrictJsonError("non-canonical JSON")
    return value


def strict_json_file(
    path: Path,
    *,
    max_bytes: int,
    require_canonical: bool = False,
) -> Any:
    try:
        status = path.lstat()
    except OSError as error:
        raise StrictJsonError("JSON file") from error
    if path.is_symlink() or not path.is_file() or status.st_size > max_bytes:
        raise StrictJsonError("JSON file")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise StrictJsonError("JSON file") from error
    return strict_json_bytes(
        payload,
        max_bytes=max_bytes,
        require_canonical=require_canonical,
    )


def require_exact_dict_keys(value: object, keys: Iterable[str]) -> dict[str, Any]:
    expected = set(keys)
    if type(value) is not dict or set(value) != expected:
        raise StrictJsonError("object schema")
    return value


def require_exact_list(value: object) -> list[Any]:
    if type(value) is not list:
        raise StrictJsonError("list type")
    return value


def require_exact_str(
    value: object,
    *,
    min_bytes: int = 0,
    max_bytes: int,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if type(value) is not str:
        raise StrictJsonError("string type")
    encoded = value.encode("utf-8")
    if not min_bytes <= len(encoded) <= max_bytes:
        raise StrictJsonError("string size")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise StrictJsonError("string syntax")
    return value


def require_exact_bool(value: object) -> bool:
    if type(value) is not bool:
        raise StrictJsonError("boolean type")
    return value


def require_exact_int(value: object, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise StrictJsonError("integer type or range")
    return value


def require_nonnegative_int(value: object, *, maximum: int) -> int:
    return require_exact_int(value, minimum=0, maximum=maximum)


def require_zero_exit(value: object) -> int:
    if type(value) is not int or value != 0:
        raise StrictJsonError("nonzero exit")
    return value


def require_enum(value: object, allowed: frozenset[str]) -> str:
    text = require_exact_str(value, min_bytes=1, max_bytes=512)
    if text not in allowed:
        raise StrictJsonError("enum")
    return text


def require_sha256(value: object) -> str:
    return require_exact_str(
        value,
        max_bytes=64,
        pattern=re.compile(r"[0-9a-f]{64}\Z"),
    )


def require_git_oid(value: object, *, length: int = 40) -> str:
    return require_exact_str(
        value,
        max_bytes=length,
        pattern=re.compile(rf"[0-9a-f]{{{length}}}\Z"),
    )


def require_relative_posix_path(value: object, *, max_bytes: int = 4096) -> str:
    text = require_exact_str(value, min_bytes=1, max_bytes=max_bytes)
    if text.startswith("/") or "\\" in text or "\x00" in text:
        raise StrictJsonError("path")
    if any(part in {"", ".", ".."} for part in text.split("/")):
        raise StrictJsonError("path")
    return text


_COMMAND_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z")


def require_timestamp(value: object) -> datetime:
    text = require_exact_str(value, max_bytes=24, pattern=_COMMAND_TIME)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise StrictJsonError("timestamp") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" != text:
        raise StrictJsonError("timestamp")
    return parsed
