"""Single fail-closed safety gate for persisted connect-loop learning data.

The scanner reports booleans and reason codes only. It must never return
matched raw text, local paths, tokens, or snippets.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator, Literal

from .scan_normalization import MAX_SCAN_CHARS, detect_any, detect_any_variants, scan_variants


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
    r"-----BEGIN[ \t]+[A-Z ]*PRIVATE KEY-----|"
    r"(?:api[ \t_-]*key|token|secret|password)\s*[:=：]|"
    r"(?:api[ \t_-]*key|token|secret|password|client[ \t_-]*secret|"
    r"private[ \t_-]*key|access[ \t_-]*key|auth[ \t_-]*key|"
    r"seed[ \t_-]*phrase)\s*[:=：]\s*[^\n\r,;]{4,}|"
    r"AKIA[0-9A-Z]{16}|"
    r"sk-[a-z0-9][a-z0-9._-]{10,})"
)
_KO_SECRET_RE = re.compile(
    r"(?:비밀번호|비번|암호|패스워드|토큰|시크릿|API[ \t_-]*키|에이피아이[ \t_-]*키|"
    r"인증[ \t_-]*키|보안[ \t_-]*키|개인[ \t_-]*키)"
    r"\s*(?:는|은|:|=|->)?\s*(?P<secret>\S+)"
)
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

    @property
    def any_detected(self) -> bool:
        return (
            self.pii_detected
            or self.secret_detected
            or self.local_path_detected
            or self.raw_field_detected
            or self.policy_violation
        )


DlpCategory = Literal["email", "phone", "korean_rrn", "card_or_account", "secret", "local_path"]
DlpOrigin = Literal["raw", "normalized"]


@dataclass(frozen=True)
class DlpCategoryFinding:
    category: DlpCategory
    variant_id: str
    pattern_id: str
    origin: DlpOrigin
    partial_redaction_safe: bool


@dataclass(frozen=True)
class DlpCategoryScanResult:
    findings: tuple[DlpCategoryFinding, ...] = ()
    too_long: bool = False
    policy_violation: bool = False

    @property
    def any_detected(self) -> bool:
        return bool(self.findings) or self.too_long or self.policy_violation


def _has_hyphenated_account(value: str) -> bool:
    for match in _ACCOUNT_HYPHEN_RE.finditer(value):
        digit_count = sum(len(match.group(group)) for group in ("g1", "g2", "g3"))
        if _PHONE_RE.fullmatch(match.group(0)):
            continue
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


_CATEGORY_PATTERNS = {
    "email": {"email": _EMAIL_RE},
    "phone": {"phone": _PHONE_RE, "phone_compact": _has_compact_phone_digits},
    "korean_rrn": {"korean_rrn": _KOREAN_RRN_RE, "korean_rrn_compact": _has_compact_korean_rrn},
    "card_or_account": {
        "card_or_account": _CARD_OR_ACCOUNT_RE,
        "card_compact": _has_compact_card_digits,
        "account_hyphenated": _has_hyphenated_account,
        "account_compact": _has_compact_account_digits,
    },
    "secret": {
        "secret": _SECRET_RE,
        "ko_secret": _has_ko_secret,
    },
    "local_path": {"local_path": _LOCAL_PATH_RE},
}
_PARTIAL_REDACTION_PATTERNS = {
    "email": _EMAIL_RE,
    "phone": _PHONE_RE,
    "korean_rrn": _KOREAN_RRN_RE,
    "card_or_account": _CARD_OR_ACCOUNT_RE,
    "account_hyphenated": _ACCOUNT_HYPHEN_RE,
}
_CANONICAL_SHA256_RE = re.compile(r"sha256:[a-f0-9]{64}")
_BARE_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_DECIMAL_DIGIT_RE = re.compile(r"\d")
_SECRET_PREFILTER_MARKERS = (
    "bearer",
    "api",
    "token",
    "secret",
    "password",
    "client",
    "private",
    "access",
    "auth",
    "seed",
    "-----begin",
    "akia",
    "sk-",
    "비밀번호",
    "비번",
    "암호",
    "패스워드",
    "토큰",
    "시크릿",
    "에이피아이",
    "인증",
    "보안",
    "개인",
)

# Compatibility exports used by focused normalization tests. New runtime callers
# consume scan_text_categories() through butler_pc_core.dlp instead.
_PII_PATTERNS = {
    pattern_id: pattern
    for category in ("email", "phone", "korean_rrn", "card_or_account")
    for pattern_id, pattern in _CATEGORY_PATTERNS[category].items()
}
_SECRET_PATTERNS = {
    "secret": _SECRET_RE,
    "ko_secret": _has_ko_secret,
}
_LOCAL_PATH_PATTERNS = {
    "local_path": _LOCAL_PATH_RE,
}


def _shield_sha256_digests(value: str) -> str:
    if _BARE_SHA256_RE.fullmatch(value):
        return "SHA256_DIGEST"
    return _CANONICAL_SHA256_RE.sub("sha256:DIGEST", value)


def _eligible_variants(category: str, variants: list[Any]) -> list[Any]:
    eligible: list[Any] = []
    for variant in variants:
        text = variant.text
        if category == "email" and "@" not in text:
            continue
        if category in {"phone", "card_or_account"} and len(_DECIMAL_DIGIT_RE.findall(text)) < 10:
            continue
        if category == "korean_rrn" and len(_DECIMAL_DIGIT_RE.findall(text)) < 13:
            continue
        if category == "secret" and not any(marker in text.casefold() for marker in _SECRET_PREFILTER_MARKERS):
            continue
        if category == "local_path" and "/" not in text and "\\" not in text and not re.search(
            r"(?i)\.(?:docx|pdf|xlsx|jsonl)\b", text
        ):
            continue
        eligible.append(variant)
    return eligible


def scan_text_categories(value: str, *, shield_digests: bool = True) -> DlpCategoryScanResult:
    """Return raw-zero category evidence from the canonical normalized scanner."""
    scan_value = str(value or "")
    if shield_digests:
        scan_value = _shield_sha256_digests(scan_value)
    if len(scan_value) > MAX_SCAN_CHARS:
        return DlpCategoryScanResult(too_long=True, policy_violation=True)

    findings: list[DlpCategoryFinding] = []
    variants = scan_variants(scan_value, runtime_optimized=True)
    for category, patterns in _CATEGORY_PATTERNS.items():
        result = detect_any_variants(patterns, _eligible_variants(category, variants))
        if not result.detected:
            continue
        variant_id = result.variant_id or "v0_raw"
        pattern_id = result.pattern_id or "unknown"
        findings.append(
            DlpCategoryFinding(
                category=category,
                variant_id=variant_id,
                pattern_id=pattern_id,
                origin="raw" if variant_id == "v0_raw" else "normalized",
                partial_redaction_safe=(
                    variant_id == "v0_raw"
                    and category not in {"secret", "local_path"}
                    and pattern_id in _PARTIAL_REDACTION_PATTERNS
                ),
            )
        )
    local_path = any(item.category == "local_path" for item in findings)
    return DlpCategoryScanResult(
        findings=tuple(findings),
        too_long=False,
        policy_violation=local_path,
    )


def redact_safe_raw_spans(value: str, replacement: str) -> str:
    """Redact only raw regex spans explicitly classified as offset-safe."""
    redacted = str(value or "")
    for pattern in _PARTIAL_REDACTION_PATTERNS.values():
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _dlp_scan_all(value: str) -> DlpScanResult:
    detailed = scan_text_categories(value)
    categories = {item.category for item in detailed.findings}
    pii = bool(categories & {"email", "phone", "korean_rrn", "card_or_account"})
    secret = "secret" in categories
    local_path = "local_path" in categories
    return DlpScanResult(
        pii_detected=pii,
        secret_detected=secret,
        local_path_detected=local_path,
        policy_violation=detailed.policy_violation,
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
