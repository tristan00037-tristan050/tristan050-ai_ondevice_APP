"""Shadow comparison record — legacy vs new Stage3Classifier, observe-only.

★ Never carries raw text, PII, account numbers, or vendor names. Free-text is stored only as a
sha256 digest. This is a side observation for Group A's 295-case comparison; it does not affect
any product response and JOURNAL_AUTO_POST_ALLOWED stays NO.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def digest_text(value: object) -> str:
    """PII-safe: sha256 of a normalized string. Used instead of storing raw memo/vendor."""
    return hashlib.sha256(str(value if value is not None else "").strip().encode("utf-8")).hexdigest()


class Agreement:
    SAME = "SAME"
    DIFFERENT_ACCOUNT = "DIFFERENT_ACCOUNT"
    SHADOW_CLASSIFIED_LEGACY_NOT = "SHADOW_CLASSIFIED_LEGACY_NOT"
    SHADOW_UNCLASSIFIED_LEGACY_CLASSIFIED = "SHADOW_UNCLASSIFIED_LEGACY_CLASSIFIED"
    BOTH_UNCLASSIFIED = "BOTH_UNCLASSIFIED"
    SHADOW_ERROR = "SHADOW_ERROR"  # shadow could not run for this row (isolated; product unaffected)


def classify_agreement(*, legacy_classified: bool, shadow_classified: bool,
                        legacy_account_id: str | None, shadow_account_id: str | None) -> str:
    if not shadow_classified and legacy_classified:
        return Agreement.SHADOW_UNCLASSIFIED_LEGACY_CLASSIFIED
    if shadow_classified and not legacy_classified:
        return Agreement.SHADOW_CLASSIFIED_LEGACY_NOT
    if not shadow_classified and not legacy_classified:
        return Agreement.BOTH_UNCLASSIFIED
    # both classified
    return Agreement.SAME if legacy_account_id == shadow_account_id else Agreement.DIFFERENT_ACCOUNT


@dataclass(frozen=True, slots=True)
class ShadowComparisonRecord:
    transaction_key: str            # anonymous key (row digest), never a real id
    legacy_status: str              # "분류됨" | "미분류"
    legacy_account_id: str | None   # legacy 분류과목 (account name/id) or None
    shadow_status: str              # AUTO_PROPOSE | REVIEW_REQUIRED | BLOCKED | UNCLASSIFIED | SHADOW_ERROR
    shadow_account_id: str | None
    shadow_rule_id: str | None
    shadow_rule_digest: str | None
    shadow_reason_code: str | None
    agreement: str
    shadow_error_code: str | None = None  # set only when shadow_status == SHADOW_ERROR
    schema_version: str = field(default="butler.box5.shadow_comparison.v1", init=False)

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "transaction_key": self.transaction_key,
            "legacy_status": self.legacy_status,
            "legacy_account_id": self.legacy_account_id,
            "shadow_status": self.shadow_status,
            "shadow_account_id": self.shadow_account_id,
            "shadow_rule_id": self.shadow_rule_id,
            "shadow_rule_digest": self.shadow_rule_digest,
            "shadow_reason_code": self.shadow_reason_code,
            "agreement": self.agreement,
            "shadow_error_code": self.shadow_error_code,
            "journal_auto_post_allowed": False,
            "auto_consumed": False,
        }

    def to_jsonl(self) -> str:
        return json.dumps(self.to_safe_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
