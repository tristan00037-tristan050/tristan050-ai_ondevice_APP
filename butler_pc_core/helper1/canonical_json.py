"""Strict Butler canonical JSON (BUTLER-CJ-1).

This codec is intentionally narrower than RFC 8259.  It is used only for
signed Helper1 approval material, where accepting two byte representations of
the same logical value would create a signature ambiguity.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


class CanonicalJsonError(ValueError):
    """Stable failure for data outside BUTLER-CJ-1."""


def _normalize_text(value: str, *, code: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    if any(0xD800 <= ord(character) <= 0xDFFF for character in normalized):
        raise CanonicalJsonError(code)
    return normalized


def _normalize(value: Any) -> Any:
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if not INT64_MIN <= value <= INT64_MAX:
            raise CanonicalJsonError("CJ1_INTEGER_OUT_OF_RANGE")
        return value
    if type(value) is str:
        return _normalize_text(value, code="CJ1_STRING_INVALID")
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for raw_key, item in value.items():
            if type(raw_key) is not str:
                raise CanonicalJsonError("CJ1_OBJECT_KEY_INVALID")
            key = _normalize_text(raw_key, code="CJ1_OBJECT_KEY_INVALID")
            if key in normalized:
                raise CanonicalJsonError("CJ1_NORMALIZED_KEY_COLLISION")
            normalized[key] = _normalize(item)
        return {key: normalized[key] for key in sorted(normalized)}
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    ):
        return [_normalize(item) for item in value]
    raise CanonicalJsonError("CJ1_TYPE_INVALID")


def canonicalize_butler_cj1(value: Any) -> bytes:
    """Return the unique UTF-8 representation for an accepted value."""
    normalized = _normalize(value)
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (UnicodeError, ValueError, TypeError) as exc:
        raise CanonicalJsonError("CJ1_ENCODING_FAILED") from exc
    if encoded.startswith(b"\xef\xbb\xbf") or encoded.endswith(b"\n"):
        raise CanonicalJsonError("CJ1_ENCODING_FAILED")
    return encoded


def _reject_float(_: str) -> None:
    raise CanonicalJsonError("CJ1_FLOAT_FORBIDDEN")


def _parse_int(value: str) -> int:
    parsed = int(value, 10)
    if not INT64_MIN <= parsed <= INT64_MAX:
        raise CanonicalJsonError("CJ1_INTEGER_OUT_OF_RANGE")
    return parsed


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    raw_seen: set[str] = set()
    for raw_key, value in pairs:
        if raw_key in raw_seen:
            raise CanonicalJsonError("CJ1_DUPLICATE_KEY")
        raw_seen.add(raw_key)
        key = _normalize_text(raw_key, code="CJ1_OBJECT_KEY_INVALID")
        if key in result:
            raise CanonicalJsonError("CJ1_NORMALIZED_KEY_COLLISION")
        result[key] = value
    return result


def loads_butler_cj1(raw: bytes) -> Any:
    """Decode strict UTF-8 JSON and reject non-canonical data types."""
    if type(raw) is not bytes or not raw or raw.startswith(b"\xef\xbb\xbf"):
        raise CanonicalJsonError("CJ1_BYTES_INVALID")
    try:
        text = raw.decode("utf-8", "strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_int=_parse_int,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except CanonicalJsonError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        raise CanonicalJsonError("CJ1_DECODE_FAILED") from exc
    return _normalize(value)


def require_canonical_butler_cj1(raw: bytes) -> Any:
    """Decode and require that the supplied bytes already are canonical."""
    value = loads_butler_cj1(raw)
    if canonicalize_butler_cj1(value) != raw:
        raise CanonicalJsonError("CJ1_NON_CANONICAL_BYTES")
    return value


def cj1_sha256(value: Any) -> str:
    return hashlib.sha256(canonicalize_butler_cj1(value)).hexdigest()
