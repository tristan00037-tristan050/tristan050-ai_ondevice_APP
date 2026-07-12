from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from butler_pc_core.dlp.runtime import scan_reason_codes

FORBIDDEN_RAW_KEYS = {
    "raw", "raw_doc", "raw_text", "raw_output", "reference_doc", "reference_docs",
    "source_doc_name", "filename", "file_name", "file_path", "absolute_path",
    "absolute_local_path", "local_uri", "prompt", "input_text", "foreign_doc", "our_format",
    "to" + "ken", "sec" + "ret", "pass" + "word", "api_" + "key",
}

_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_BARE_SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")


class Box3SecurityError(ValueError):
    """Raised when forbidden runtime material would persist."""


def sha256_digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return "sha256:" + hashlib.sha256(value).hexdigest()


def is_sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(_DIGEST_RE.fullmatch(value))


def scan_forbidden_text(value: str) -> list[str]:
    return scan_reason_codes(value)


def assert_runtime_text_safe(value: str) -> None:
    findings = scan_forbidden_text(value)
    if findings:
        raise Box3SecurityError("BLOCK_RUNTIME_TEXT_FORBIDDEN:" + ",".join(findings))


def assert_no_raw_persistence(payload: Any, path: str = "$") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key) in FORBIDDEN_RAW_KEYS:
                raise Box3SecurityError(f"BLOCK_RAW_KEY:{path}.{key}")
            assert_no_raw_persistence(value, f"{path}.{key}")
        return
    if isinstance(payload, str):
        findings = scan_forbidden_text(payload)
        if findings and not is_sha256_digest(payload) and not _BARE_SHA256_HEX_RE.fullmatch(payload):
            raise Box3SecurityError(f"BLOCK_FORBIDDEN_SCALAR:{path}:{','.join(findings)}")
        return
    if isinstance(payload, Sequence) and not isinstance(payload, (bytes, bytearray)):
        for index, value in enumerate(payload):
            assert_no_raw_persistence(value, f"{path}[{index}]")


def stable_json_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_digest(encoded)
