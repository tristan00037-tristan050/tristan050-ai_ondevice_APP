"""Runtime-only DLP guard for PR-E.

The guard returns booleans only. It never returns matched raw text, file names,
local paths, tokens, or snippets.
"""
from __future__ import annotations

import re
from typing import Any


FORBIDDEN_RAW_KEYS = {
    "raw",
    "raw_text",
    "raw_query",
    "raw_answer",
    "raw_source_text",
    "raw_input",
    "raw_output",
    "source_doc_name",
    "file_name",
    "filename",
    "absolute_local_path",
    "local_path",
    "token",
    "secret",
    "password",
    "api_key",
}

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?82[-.\s]?)?0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}\b")
_KOREAN_RRN_RE = re.compile(r"\b\d{6}-[1-4]\d{6}\b")
_CARD_OR_ACCOUNT_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_SECRET_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~+/=-]{10,}|api[_-]?key\s*[:=]|token\s*[:=]|secret\s*[:=]|password\s*[:=]|sk-[a-z0-9]{12,})"
)
_LOCAL_PATH_RE = re.compile(r"(/Users/|/Volumes/|[A-Za-z]:\\|file://|\.docx\b|\.pdf\b|\.xlsx\b|\.jsonl\b)")


def scan_runtime_text(text: str) -> dict[str, bool]:
    pii = bool(
        _EMAIL_RE.search(text)
        or _PHONE_RE.search(text)
        or _KOREAN_RRN_RE.search(text)
        or _CARD_OR_ACCOUNT_RE.search(text)
    )
    secret = bool(_SECRET_RE.search(text))
    policy_violation = bool(_LOCAL_PATH_RE.search(text))
    return {
        "passed": not (pii or secret or policy_violation),
        "pii_detected": pii,
        "secret_detected": secret,
        "policy_violation": policy_violation,
    }


def _contains_forbidden_scalar(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_SECRET_RE.search(value) or _LOCAL_PATH_RE.search(value))


def assert_no_raw_or_secret_material(value: Any) -> None:
    """Fail closed if an object contains raw-like keys or forbidden strings."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in FORBIDDEN_RAW_KEYS:
                raise ValueError("RAW_OR_SECRET_FIELD_FORBIDDEN")
            assert_no_raw_or_secret_material(item)
        return
    if isinstance(value, list):
        for item in value:
            assert_no_raw_or_secret_material(item)
        return
    if _contains_forbidden_scalar(value):
        raise ValueError("RAW_OR_SECRET_VALUE_FORBIDDEN")
