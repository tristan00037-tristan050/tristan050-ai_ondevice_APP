"""Single fail-closed safety gate for persisted connect-loop learning data.

The scanner reports booleans and reason codes only. It must never return
matched raw text, local paths, tokens, normalized variants, or snippets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator

from .scan_normalization import detect_any

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

RAW_SAVED_FALSE_KEYS = {
    "raw_input_saved",
    "raw_output_saved",
    "sanitized_summary_saved",
}

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?x)(?<!\w)(?:"
    r"(?:\+?82[-.\s]?)?0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}|"
    r"\+?82[-.\s]?\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}|"
    r"(?:\+?[1-9]\d{0,2}[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}"
    r")(?!\w)"
)
_KOREAN_RRN_RE = re.compile(r"\b\d{6}-[1-4]\d{6}\b")
_CARD_OR_ACCOUNT_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_HYPHEN_CHARS = r"[-‐‑‒–—―﹣－]"
_ACCOUNT_HYPHEN_RE = re.compile(
    rf"(?<!\d)(?P<g1>\d{{2,6}}){_HYPHEN_CHARS}"
    rf"(?P<g2>\d{{2,6}}){_HYPHEN_CHARS}"
    rf"(?P<g3>\d{{2,8}})(?!\d)"
)
_SECRET_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~+/=-]{10,}|"
    r"api[_-]?key\s*[:=]|"
    r"token\s*[:=]|"
    r"secret\s*[:=]|"
    r"password\s*[:=]|"
    r"AKIA[0-9A-Z]{16}|"
    r"sk-[a-z0-9][a-z0-9._-]{10,})"
)
_KO_SECRET_RE = re.compile(r"(비밀번호|비번|암호)\s*(?:는|은|:|=|->)?\s*(?P<secret>\S+)")
_KO_SECRET_SAFE_START = ("정책", "규칙", "변경", "초기화", "재설정", "관리", "설정")
_LOCAL_PATH_RE = re.compile(
    r"(?i)(file://|"
    r"/Users(?:/|$)|"
    r"/home(?:/|$)|"
    r"/tmp(?:/|$)|"
    r"/private/tmp(?:/|$)|"
    r"/Volumes(?:/|$)|"
    r"(?<![A-Za-z0-9])[A-Z]:[\\/]|"
    r"\\\\[A-Za-z0-9._$-]+\\[A-Za-z0-9._$-]+|"
    r"\.(?:docx|pdf|xlsx|jsonl)\b)"
)


class PersistedSafetyViolation(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class DlpScanResult:
    pii_detected: bool = False
    secret_detected: bool = False
    local_path_detected: bool = False
    raw_field_detected: bool = False
    policy_violation: bool = False
    scan_too_long: bool = False

    @property
    def any_detected(self) -> bool:
        return (
            self.pii_detected
            or self.secret_detected
            or self.local_path_detected
            or self.raw_field_detected
            or self.policy_violation
            or self.scan_too_long
        )


def _has_hyphenated_account(value: str) -> bool:
    for match in _ACCOUNT_HYPHEN_RE.finditer(value):
        digit_count = sum(len(match.group(group)) for group in ("g1", "g2", "g3"))
        if 10 <= digit_count <= 20:
            return True
    return False


def _has_ko_secret_signal(token: str) -> bool:
    return any(char.isdigit() or (char.isascii() and char.isalnum()) or char in "!@#$%^&*_" for char in token)


def _has_ko_secret(value: str) -> bool:
    for match in _KO_SECRET_RE.finditer(value):
        token = match.group("secret").strip("'\"`“”‘’()[]{}")
        if token.startswith(_KO_SECRET_SAFE_START) and not _has_ko_secret_signal(token):
            continue
        if _has_ko_secret_signal(token):
            return True
    return False


_PII_PATTERNS = {
    "email": _EMAIL_RE,
    "phone": _PHONE_RE,
    "korean_rrn": _KOREAN_RRN_RE,
    "card_or_account": _CARD_OR_ACCOUNT_RE,
    "hyphenated_account": _has_hyphenated_account,
}
_SECRET_PATTERNS = {
    "secret": _SECRET_RE,
    "ko_secret": _has_ko_secret,
}
_LOCAL_PATH_PATTERNS = {
    "local_path": _LOCAL_PATH_RE,
}


def _dlp_scan_all(value: str) -> DlpScanResult:
    raw = str(value or "")
    pii = detect_any(_PII_PATTERNS, raw)
    secret = detect_any(_SECRET_PATTERNS, raw)
    local_path = detect_any(_LOCAL_PATH_PATTERNS, raw)
    too_long = pii.too_long or secret.too_long or local_path.too_long
    return DlpScanResult(
        pii_detected=pii.detected and not pii.too_long,
        secret_detected=secret.detected and not secret.too_long,
        local_path_detected=local_path.detected and not local_path.too_long,
        policy_violation=(local_path.detected or too_long),
        scan_too_long=too_long,
    )


def _walk_scalars(obj: Any, key: str | None = None, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], str | None, Any]]:
    if isinstance(obj, dict):
        for child_key, child_value in obj.items():
            yield from _walk_scalars(child_value, str(child_key), path + (str(child_key),))
        return
    if isinstance(obj, list):
        for index, child_value in enumerate(obj):
            yield from _walk_scalars(child_value, None, path + (str(index),))
        return
    yield path, key, obj


def _is_forbidden_field_value(key: str | None, value: Any) -> bool:
    if key is None:
        return False
    lowered = key.lower()
    if lowered in RAW_SAVED_FALSE_KEYS:
        return value is not False
    if lowered in FORBIDDEN_RAW_KEYS:
        return True
    if lowered.endswith("_raw"):
        return True
    if lowered.endswith("_saved") and value is True:
        return True
    return False


def _enforce_persisted_safety(obj: Any) -> None:
    for _path, key, value in _walk_scalars(obj):
        if _is_forbidden_field_value(key, value):
            raise PersistedSafetyViolation("RAW_FIELD_OR_SAVED_TRUE")
        if isinstance(value, str) and _dlp_scan_all(value).any_detected:
            raise PersistedSafetyViolation("PERSISTED_SCALAR_DLP_BLOCK")
