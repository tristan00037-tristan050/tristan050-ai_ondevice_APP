"""Canonical raw-zero DLP scanner for persisted and runtime Butler paths.

Pattern definitions remain the single SSOT. Public consumers use
``scan_text_categories``; the private ``_dlp_scan_all`` wrapper is retained for
legacy persisted-learning contracts only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator, Literal

from .scan_normalization import SCAN_INPUT_TOO_LONG, detect_grouped

FORBIDDEN_RAW_KEYS = {
    "raw", "raw_text", "raw_query", "raw_answer", "raw_source_text", "raw_input", "raw_output",
    "source_doc_name", "file_name", "filename", "absolute_local_path", "local_path", "token",
    "secret", "password", "api_key",
}
RAW_SAVED_FALSE_KEYS = {"raw_input_saved", "raw_output_saved", "sanitized_summary_saved"}

# Do not reformat these assignments: existing digest guards bind the canonical patterns.
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
_ACCOUNT_CONTEXT_RE = re.compile(r"(?i)(계좌|입금|상환|예금|account|acct)")
_CARD_CONTEXT_RE = re.compile(r"(?i)(카드|card)")
_PHONE_CONTEXT_RE = re.compile(r"(?i)(전화|연락|휴대폰|phone|tel|mobile)")
_RRN_CONTEXT_RE = re.compile(r"(?i)(주민|주민등록|rrn|resident)")
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
_DIGEST_SPAN_RE = re.compile(r"(?<![A-Fa-f0-9])(?:sha256:)?[A-Fa-f0-9]{64}(?![A-Fa-f0-9])")

DlpCategory = Literal["email", "phone", "korean_rrn", "card_or_account", "secret", "local_path"]


class PersistedSafetyViolation(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class PersistedDlpFinding:
    category: DlpCategory
    variant_id: str
    pattern_id: str
    partial_redaction_safe: bool


@dataclass(frozen=True)
class PersistedDlpScanResult:
    findings: tuple[PersistedDlpFinding, ...] = ()
    too_long: bool = False
    policy_violation: bool = False

    @property
    def any_detected(self) -> bool:
        return bool(self.findings) or self.too_long or self.policy_violation


@dataclass(frozen=True)
class DlpScanResult:
    """Legacy aggregate returned by ``_dlp_scan_all``."""

    pii_detected: bool = False
    secret_detected: bool = False
    local_path_detected: bool = False
    raw_field_detected: bool = False
    policy_violation: bool = False

    @property
    def any_detected(self) -> bool:
        return self.pii_detected or self.secret_detected or self.local_path_detected or self.raw_field_detected or self.policy_violation


def _has_hyphenated_account(value: str) -> bool:
    for match in _ACCOUNT_HYPHEN_RE.finditer(value):
        candidate = match.group(0)
        if _PHONE_RE.fullmatch(candidate) or _KOREAN_RRN_RE.fullmatch(candidate):
            continue
        digit_count = sum(len(match.group(group)) for group in ("g1", "g2", "g3"))
        if 10 <= digit_count <= 20:
            return True
    return False


def _has_compact_account_digits(value: str) -> bool:
    stripped = value.strip()
    if re.fullmatch(r"\d{10,20}", stripped):
        return True
    if not _ACCOUNT_CONTEXT_RE.search(value):
        return False
    return any(10 <= match.end() - match.start() <= 20 for match in re.finditer(r"(?<!\d)\d{10,20}(?!\d)", value))


def _has_compact_card_digits(value: str) -> bool:
    stripped = value.strip()
    if re.fullmatch(r"\d{13,19}", stripped):
        return True
    if not _CARD_CONTEXT_RE.search(value):
        return False
    return any(13 <= match.end() - match.start() <= 19 for match in re.finditer(r"(?<!\d)\d{13,19}(?!\d)", value))


def _has_compact_phone_digits(value: str) -> bool:
    stripped = value.strip()
    if re.fullmatch(r"(?:0\d{9,10}|82\d{8,10})", stripped):
        return True
    if not _PHONE_CONTEXT_RE.search(value):
        return False
    return bool(re.search(r"(?<!\d)(?:0\d{9,10}|82\d{8,10})(?!\d)", value))


def _has_compact_korean_rrn(value: str) -> bool:
    stripped = value.strip()
    if re.fullmatch(r"\d{6}[1-4]\d{6}", stripped):
        return True
    return bool(_RRN_CONTEXT_RE.search(value) and re.search(r"(?<!\d)\d{6}[1-4]\d{6}(?!\d)", value))


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
    "korean_rrn_compact": _has_compact_korean_rrn,
    "card_or_account": _CARD_OR_ACCOUNT_RE,
    "card_compact": _has_compact_card_digits,
    "phone_compact": _has_compact_phone_digits,
    "account_hyphenated": _has_hyphenated_account,
    "account_compact": _has_compact_account_digits,
}
_SECRET_PATTERNS = {"secret": _SECRET_RE, "ko_secret": _has_ko_secret}
_LOCAL_PATH_PATTERNS = {"local_path": _LOCAL_PATH_RE}

_PATTERN_CATEGORY: dict[str, DlpCategory] = {
    "email": "email",
    "phone": "phone",
    "phone_compact": "phone",
    "korean_rrn": "korean_rrn",
    "korean_rrn_compact": "korean_rrn",
    "card_or_account": "card_or_account",
    "card_compact": "card_or_account",
    "account_hyphenated": "card_or_account",
    "account_compact": "card_or_account",
    "secret": "secret",
    "ko_secret": "secret",
    "local_path": "local_path",
}
_PARTIAL_REDACTION_SAFE_PATTERNS = frozenset({"email", "phone", "korean_rrn", "card_or_account"})
_ALL_PATTERNS = {**_PII_PATTERNS, **_SECRET_PATTERNS, **_LOCAL_PATH_PATTERNS}


def _max_decimal_digits_in_token(value: str) -> int:
    """Count decimal digits in the densest whitespace-delimited token.

    This deliberately preserves whitespace boundaries so an unrelated date and
    time do not become one phone/account candidate. Python's ``\\d`` is Unicode
    decimal-aware and executes in C, avoiding a Python per-character hot loop.
    """
    maximum = 0
    for token in re.split(r"\s+", value):
        if not token:
            continue
        count = len(re.findall(r"\d", token))
        if count > maximum:
            maximum = count
    return maximum


def _candidate_groups(value: str) -> dict[str, dict[str, Any]]:
    folded = value.casefold()
    max_digits = _max_decimal_digits_in_token(value)
    groups: dict[str, dict[str, Any]] = {}
    if "@" in value or "＠" in value:
        groups["email"] = {"email": _EMAIL_RE}
    if max_digits >= 9 or _PHONE_CONTEXT_RE.search(value):
        groups["phone"] = {"phone": _PHONE_RE, "phone_compact": _has_compact_phone_digits}
    if max_digits >= 13 or _RRN_CONTEXT_RE.search(value):
        groups["korean_rrn"] = {"korean_rrn": _KOREAN_RRN_RE, "korean_rrn_compact": _has_compact_korean_rrn}
    if max_digits >= 10 or _ACCOUNT_CONTEXT_RE.search(value) or _CARD_CONTEXT_RE.search(value):
        groups["card_or_account"] = {
            "card_or_account": _CARD_OR_ACCOUNT_RE,
            "card_compact": _has_compact_card_digits,
            "account_hyphenated": _has_hyphenated_account,
            "account_compact": _has_compact_account_digits,
        }
    if any(token in folded for token in ("bearer", "api", "token", "secret", "password", "sk-", "akia", "private key", "비밀번호", "비번", "암호")):
        groups["secret"] = _SECRET_PATTERNS
    if any(token in folded for token in ("file://", "/users", "/home", "/tmp", "/private/tmp", "/volumes", ".docx", ".pdf", ".xlsx", ".jsonl", "\\")) or re.search(r"(?<![A-Za-z0-9])[A-Z]:[\\/]", value):
        groups["local_path"] = _LOCAL_PATH_PATTERNS
    return groups


def scan_text_categories(value: str) -> PersistedDlpScanResult:
    """Return one canonical raw-zero finding per category."""
    raw = str(value or "")
    groups = _candidate_groups(raw)
    results = detect_grouped(groups, raw)
    too_long = "__too_long__" in results
    if too_long:
        return PersistedDlpScanResult((), too_long=True, policy_violation=True)
    findings: list[PersistedDlpFinding] = []
    for category in ("email", "phone", "korean_rrn", "card_or_account", "secret", "local_path"):
        hit = results.get(category)
        if hit is None or hit.variant_id is None or hit.pattern_id is None:
            continue
        findings.append(
            PersistedDlpFinding(
                category=category,
                variant_id=hit.variant_id,
                pattern_id=hit.pattern_id,
                partial_redaction_safe=hit.pattern_id in _PARTIAL_REDACTION_SAFE_PATTERNS and hit.variant_id == "v0_raw",
            )
        )
    local_path = any(item.category == "local_path" for item in findings)
    return PersistedDlpScanResult(tuple(findings), too_long=False, policy_violation=local_path)


def _dlp_scan_all(value: str) -> DlpScanResult:
    """Legacy boolean aggregate; new code must use ``scan_text_categories``."""
    result = scan_text_categories(value)
    categories = {item.category for item in result.findings}
    return DlpScanResult(
        pii_detected=bool(categories & {"email", "phone", "korean_rrn", "card_or_account"}),
        secret_detected="secret" in categories,
        local_path_detected="local_path" in categories,
        policy_violation=result.policy_violation or result.too_long,
    )


def _overlaps_digest(start: int, end: int, digest_spans: tuple[tuple[int, int], ...]) -> bool:
    return any(start < digest_end and end > digest_start for digest_start, digest_end in digest_spans)


def redact_safe_raw_pii_spans(value: str, replacement: str) -> str:
    """Redact only raw regex PII spans while shielding canonical/bare SHA-256."""
    text = str(value or "")
    digest_spans = tuple((match.start(), match.end()) for match in _DIGEST_SPAN_RE.finditer(text))
    spans: list[tuple[int, int]] = []
    for pattern in (_EMAIL_RE, _PHONE_RE, _KOREAN_RRN_RE, _CARD_OR_ACCOUNT_RE):
        for match in pattern.finditer(text):
            if not _overlaps_digest(match.start(), match.end(), digest_spans):
                spans.append((match.start(), match.end()))
    if not spans:
        return text
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    parts: list[str] = []
    cursor = 0
    for start, end in merged:
        parts.extend((text[cursor:start], replacement))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


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
    if lowered in FORBIDDEN_RAW_KEYS or lowered.endswith("_raw"):
        return True
    if lowered.endswith("_saved") and value is True:
        return True
    return False


def _enforce_persisted_safety(obj: Any) -> None:
    for _path, key, value in _walk_scalars(obj):
        if _is_forbidden_field_value(key, value):
            raise PersistedSafetyViolation("RAW_FIELD_OR_SAVED_TRUE")
        if isinstance(value, str) and scan_text_categories(value).any_detected:
            raise PersistedSafetyViolation("PERSISTED_SCALAR_DLP_BLOCK")
