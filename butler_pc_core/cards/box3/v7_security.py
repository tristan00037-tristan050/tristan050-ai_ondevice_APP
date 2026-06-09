from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_SHA_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_BARE_SHA_RE = re.compile(r"^[a-f0-9]{64}$")
_FORBIDDEN_KEYS = (
    "raw_doc", "raw_text", "prompt_text", "output_text", "snippet", "absolute_path", "file_path",
    "reference_text", "draft_text_runtime", "reference_text_runtime_only", "drafting_request_runtime",
)
_FORBIDDEN_SCALARS = (
    "/Users/", "/home/", "/Volumes/", "sk-proj-", "BEGIN PRIVATE KEY", "api_key", "secret_key",
)


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def stable_json_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(encoded)


def is_sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA_RE.fullmatch(value))


def is_bare_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_BARE_SHA_RE.fullmatch(value))


def assert_digest_only(value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    lowered = encoded.casefold()
    for key in _FORBIDDEN_KEYS:
        if key.casefold() in lowered:
            raise AssertionError(f"raw-like key leaked: {key}")
    for scalar in _FORBIDDEN_SCALARS:
        if scalar in encoded:
            raise AssertionError(f"forbidden scalar leaked: {scalar}")
