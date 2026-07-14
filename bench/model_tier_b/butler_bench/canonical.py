from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import Path
from typing import Any

from .errors import ExitCode, FailClass, GateError

MAX_SAFE_INTEGER = (1 << 53) - 1


def _validate(value: Any, path: str = "$") -> None:
    """Validate the deterministic I-JSON profile used by Butler receipts.

    RFC 8785 permits IEEE-754 numbers.  Butler receipts intentionally use
    integer base units (nanoseconds, bytes, ppm) and reject floats, avoiding
    cross-runtime rounding ambiguity.  Policy decimal thresholds are normalized
    to strings by policy.py before canonicalization.
    """
    if value is None or isinstance(value, (bool, str)):
        if isinstance(value, str):
            if unicodedata.normalize("NFC", value) != value:
                raise GateError(FailClass.SCHEMA_INVALID, "STRING_NOT_NFC", exit_code=ExitCode.SCHEMA)
            if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
                raise GateError(FailClass.SCHEMA_INVALID, "LONE_SURROGATE", exit_code=ExitCode.SCHEMA)
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > MAX_SAFE_INTEGER:
            raise GateError(FailClass.SCHEMA_INVALID, "INTEGER_OUTSIDE_IJSON", exit_code=ExitCode.SCHEMA)
        return
    if isinstance(value, float):
        reason = "NONFINITE_NUMBER" if not math.isfinite(value) else "FLOAT_FORBIDDEN_USE_SCALED_INTEGER"
        raise GateError(FailClass.SCHEMA_INVALID, reason, exit_code=ExitCode.SCHEMA)
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise GateError(FailClass.SCHEMA_INVALID, "NON_STRING_KEY", exit_code=ExitCode.SCHEMA)
            _validate(key, f"{path}.<key>")
            _validate(item, f"{path}.{key}")
        return
    raise GateError(FailClass.SCHEMA_INVALID, "UNSUPPORTED_JSON_TYPE", exit_code=ExitCode.SCHEMA)


def canonical_bytes(value: Any) -> bytes:
    _validate(value)
    return _encode(value).encode("utf-8")


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        # RFC 8785 sorts property names as arrays of UTF-16 code units.
        ordered = sorted(value, key=lambda key: key.encode("utf-16be"))
        return "{" + ",".join(f"{_encode(key)}:{_encode(value[key])}" for key in ordered) + "}"
    raise AssertionError("validated JSON type missing encoder")


def sha256_bytes(data: bytes | bytearray | memoryview) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def write_canonical_json(path: Path, value: Any) -> str:
    payload = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload + b"\n")
    return sha256_bytes(payload)


def read_json_closed(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise GateError(FailClass.SCHEMA_INVALID, "JSON_READ_FAILED", exit_code=ExitCode.SCHEMA) from None


def _reject_constant(_: str) -> None:
    raise ValueError("non-finite number")


def _reject_float(_: str) -> None:
    raise ValueError("floating point JSON is forbidden; use scaled integers or decimal strings")


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
