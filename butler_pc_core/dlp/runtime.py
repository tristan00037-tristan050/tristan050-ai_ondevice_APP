"""Public runtime DLP facade for Butler cards and sidecar adapters.

The facade preserves per-card semantics: Box3 consumes stable block reason codes,
while Box4/Box6 use fail-closed redaction. No API returns raw matches, snippets,
offsets, file paths, or normalized text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from butler_pc_core.connect_loop.persisted_safety import (
    PersistedDlpFinding,
    redact_safe_raw_pii_spans,
    scan_text_categories,
)

SAFE_SECRET_REPLACEMENT = "[민감정보 원문 생략]"

DlpCategory = Literal["email", "phone", "korean_rrn", "card_or_account", "secret", "local_path"]
DlpOrigin = Literal["raw", "normalized"]

_DIGEST_RE = re.compile(r"(?<![A-Fa-f0-9])(?:sha256:)?[A-Fa-f0-9]{64}(?![A-Fa-f0-9])")
_PII_CATEGORIES = frozenset({"email", "phone", "korean_rrn", "card_or_account"})
_LEGACY_REASON_ORDER: tuple[tuple[DlpCategory, str], ...] = (
    ("email", "PII_EMAIL"),
    ("korean_rrn", "PII_KOREAN_RRN"),
    ("phone", "PII_PHONE"),
    ("card_or_account", "PII_CARD_OR_ACCOUNT"),
    ("secret", "SECRET"),
    ("local_path", "LOCAL_PATH"),
)


@dataclass(frozen=True)
class RuntimeDlpFinding:
    category: DlpCategory
    legacy_reason_code: str
    variant_id: str
    pattern_id: str
    origin: DlpOrigin
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

    @property
    def pii_detected(self) -> bool:
        return any(item.category in _PII_CATEGORIES for item in self.findings)

    @property
    def secret_detected(self) -> bool:
        return any(item.category == "secret" for item in self.findings)

    @property
    def local_path_detected(self) -> bool:
        return any(item.category == "local_path" for item in self.findings)


def _shield_digests(text: str) -> str:
    return _DIGEST_RE.sub("DIGEST", text)


def _legacy_reason(category: DlpCategory) -> str:
    for item_category, reason in _LEGACY_REASON_ORDER:
        if item_category == category:
            return reason
    raise ValueError("DLP_CATEGORY_INVALID")


def _to_runtime_finding(item: PersistedDlpFinding) -> RuntimeDlpFinding:
    origin: DlpOrigin = "raw" if item.variant_id == "v0_raw" else "normalized"
    return RuntimeDlpFinding(
        category=item.category,
        legacy_reason_code=_legacy_reason(item.category),
        variant_id=item.variant_id,
        pattern_id=item.pattern_id,
        origin=origin,
        partial_redaction_safe=item.partial_redaction_safe,
    )


def scan_runtime(text: str, *, shield_digests: bool = True) -> RuntimeDlpScanResult:
    value = str(text or "")
    scan_value = _shield_digests(value) if shield_digests else value
    result = scan_text_categories(scan_value)
    findings = tuple(_to_runtime_finding(item) for item in result.findings)
    return RuntimeDlpScanResult(
        findings=findings,
        too_long=result.too_long,
        policy_violation=result.policy_violation,
    )


def scan_reason_codes(text: str) -> list[str]:
    """Box3-compatible stable six-code block contract."""
    result = scan_runtime(text)
    categories = {item.category for item in result.findings}
    codes = [reason for category, reason in _LEGACY_REASON_ORDER if category in categories]
    # Legacy Box3 has no seventh code. Too-long is conservatively represented by
    # LOCAL_PATH, the existing policy-violation bucket, so the stage schema stays stable.
    if result.too_long and "LOCAL_PATH" not in codes:
        codes.append("LOCAL_PATH")
    return codes


def _requires_full_scalar_redaction(result: RuntimeDlpScanResult) -> bool:
    if result.too_long or result.policy_violation:
        return True
    return any(
        item.origin == "normalized"
        or not item.partial_redaction_safe
        or item.category in {"secret", "local_path"}
        for item in result.findings
    )


def redact_fail_closed(text: str, replacement: str = SAFE_SECRET_REPLACEMENT) -> str:
    """Redact runtime output without ever leaving a normalized/callable residual.

    Only raw-regex, full-span-safe PII may be partially replaced. Every other hit
    replaces the complete scalar. A mandatory post-redaction rescan prevents
    detector/redactor span disagreement from leaking a value.
    """
    value = str(text or "")
    first = scan_runtime(value)
    if not first.any_detected:
        return value
    if _requires_full_scalar_redaction(first):
        return replacement
    candidate = redact_safe_raw_pii_spans(value, replacement)
    if candidate == value:
        return replacement
    if scan_runtime(candidate).any_detected:
        return replacement
    return candidate


__all__ = [
    "SAFE_SECRET_REPLACEMENT",
    "RuntimeDlpFinding",
    "RuntimeDlpScanResult",
    "scan_runtime",
    "scan_reason_codes",
    "redact_fail_closed",
]
