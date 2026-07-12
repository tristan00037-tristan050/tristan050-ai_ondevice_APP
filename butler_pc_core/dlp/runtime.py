"""Raw-zero runtime facade over Butler's canonical normalized DLP scanner."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from butler_pc_core.connect_loop.persisted_safety import (
    redact_safe_raw_spans,
    scan_text_categories,
)


SAFE_SECRET_REPLACEMENT = "[민감정보 원문 생략]"

Category = Literal["email", "phone", "korean_rrn", "card_or_account", "secret", "local_path"]
Origin = Literal["raw", "normalized"]

_LEGACY_REASON_ORDER: tuple[tuple[Category, str], ...] = (
    ("email", "PII_EMAIL"),
    ("korean_rrn", "PII_KOREAN_RRN"),
    ("phone", "PII_PHONE"),
    ("card_or_account", "PII_CARD_OR_ACCOUNT"),
    ("secret", "SECRET"),
    ("local_path", "LOCAL_PATH"),
)
_LEGACY_REASON_BY_CATEGORY = dict(_LEGACY_REASON_ORDER)


@dataclass(frozen=True)
class RuntimeDlpFinding:
    category: Category
    legacy_reason_code: str
    variant_id: str
    pattern_id: str
    origin: Origin
    partial_redaction_safe: bool


@dataclass(frozen=True)
class RuntimeDlpScanResult:
    findings: tuple[RuntimeDlpFinding, ...] = ()
    too_long: bool = False
    policy_violation: bool = False

    @property
    def any_detected(self) -> bool:
        return bool(self.findings) or self.too_long or self.policy_violation

    @property
    def normalized_only(self) -> bool:
        return bool(self.findings) and all(item.origin == "normalized" for item in self.findings)


def scan_runtime(text: str, *, shield_digests: bool = True) -> RuntimeDlpScanResult:
    detailed = scan_text_categories(text, shield_digests=shield_digests)
    findings = tuple(
        RuntimeDlpFinding(
            category=item.category,
            legacy_reason_code=_LEGACY_REASON_BY_CATEGORY[item.category],
            variant_id=item.variant_id,
            pattern_id=item.pattern_id,
            origin=item.origin,
            partial_redaction_safe=item.partial_redaction_safe,
        )
        for item in detailed.findings
    )
    return RuntimeDlpScanResult(
        findings=findings,
        too_long=detailed.too_long,
        policy_violation=detailed.policy_violation,
    )


def scan_reason_codes(text: str) -> list[str]:
    categories = {item.category for item in scan_runtime(text).findings}
    return [reason for category, reason in _LEGACY_REASON_ORDER if category in categories]


def _must_full_scalar_redact(result: RuntimeDlpScanResult) -> bool:
    if result.too_long or result.policy_violation:
        return True
    return any(
        item.origin == "normalized"
        or not item.partial_redaction_safe
        or item.category in {"secret", "local_path"}
        for item in result.findings
    )


def redact_fail_closed(text: str, replacement: str = SAFE_SECRET_REPLACEMENT) -> str:
    first = scan_runtime(text)
    if not first.any_detected:
        return text
    if _must_full_scalar_redact(first):
        return replacement

    candidate = redact_safe_raw_spans(text, replacement)
    if candidate == text:
        return replacement
    if scan_runtime(candidate).any_detected:
        return replacement
    return candidate
