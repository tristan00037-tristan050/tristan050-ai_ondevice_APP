"""Independent integer-only RFC 8785 profile used at the A4 trust boundary."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Mapping
from typing import Any


SIGNATURE_DOMAIN = b"BUTLER-A4-ATTESTATION-V5.3\x00"


class CanonicalError(ValueError):
    pass


def _string(value: str) -> bytes:
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise CanonicalError("BLOCK_REQUEST_SCHEMA")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def jcs_bytes(value: Any) -> bytes:
    """Return canonical bytes for the A4 integer-only I-JSON profile."""

    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if type(value) is int:
        return str(value).encode("ascii")
    if isinstance(value, float):
        raise CanonicalError("BLOCK_REQUEST_SCHEMA")
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return b"[" + b",".join(jcs_bytes(item) for item in value) + b"]"
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CanonicalError("BLOCK_REQUEST_SCHEMA")
        keys = sorted(value, key=lambda key: key.encode("utf-16-be", "surrogatepass"))
        return b"{" + b",".join(
            _string(key) + b":" + jcs_bytes(value[key]) for key in keys
        ) + b"}"
    raise CanonicalError("BLOCK_REQUEST_SCHEMA")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def attestation_envelope(canonical_receipt: bytes) -> bytes:
    if not canonical_receipt:
        raise CanonicalError("BLOCK_REQUEST_SCHEMA")
    return SIGNATURE_DOMAIN + struct.pack(">Q", len(canonical_receipt)) + canonical_receipt


def receipt_signing_bytes(receipt_without_signature: Mapping[str, Any]) -> bytes:
    return attestation_envelope(jcs_bytes(receipt_without_signature))
