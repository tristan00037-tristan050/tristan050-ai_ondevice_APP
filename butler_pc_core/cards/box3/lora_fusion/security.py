from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
BARE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_FORBIDDEN_KEYS = {
    "raw_text", "raw_prompt", "raw_output", "raw_reference", "prompt", "output",
    "absolute_path", "file_path", "filename", "source_doc_name", "local_uri",
    "token", "password", "secret", "api_key",
}
_FORBIDDEN_SCALARS = (
    "/Users/", "/home/", "/Volumes/", "C:\\\\", "sk-proj-", "Bearer ", "BEGIN PRIVATE KEY",
)


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def stable_json_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(raw)


def is_sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def is_bare_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(BARE_SHA256_RE.fullmatch(value))


def assert_no_raw_or_path_material(value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    lowered = encoded.casefold()
    for key in _FORBIDDEN_KEYS:
        if key.casefold() in lowered and "raw_saved_zero" not in lowered:
            raise ValueError(f"RAW_OR_SECRET_FIELD_FORBIDDEN:{key}")
    for scalar in _FORBIDDEN_SCALARS:
        if scalar in encoded:
            raise ValueError("RAW_OR_SECRET_VALUE_FORBIDDEN")


def assert_ref_or_digest(value: str | None) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError("REF_OR_DIGEST_INVALID")
    if value.startswith("ref:"):
        return
    if value.startswith("asset-role:"):
        return
    if is_sha256_digest(value):
        return
    raise ValueError("REF_OR_DIGEST_INVALID")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
