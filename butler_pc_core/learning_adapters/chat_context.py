from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.learning_core.contracts import (
    GateResult,
    IntegratedLearningError,
    is_sha256,
    validate_evidence_ref,
    validate_verified_at,
    validate_verified_by,
)

CHAT_CONTEXT_PAYLOAD_FIELDS = frozenset(
    {
        "explicit_business_confirmation",
        "manager_or_admin_approved",
        "shadow_eval_cases",
        "pii_zero",
        "false_learning_zero",
        "context_digest",
    }
)
CHAT_CONTEXT_SOURCE_REF_FIELDS = frozenset({"ref_type", "ref_id_digest"})
CHAT_CONTEXT_ALLOWED_SOURCE_TYPES = frozenset({"usage_log", "approval"})
CHAT_CONTEXT_VERIFICATION_FIELDS = frozenset(
    {"verified_by", "verified_at", "evidence_digest", "evidence_ref"}
)


@dataclass(frozen=True)
class ChatContextAdapter:
    target_kind: str = "chat_context"
    enabled: bool = False

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        if not self.enabled:
            return GateResult.drop("CHAT_CONTEXT_DISABLED")

        provenance_reason = validate_chat_context_provenance(candidate)
        if provenance_reason is not None:
            return GateResult.drop(provenance_reason)

        source_ref_reason = validate_chat_context_source_refs(candidate)
        if source_ref_reason is not None:
            return GateResult.drop(source_ref_reason)

        payload = candidate.get("payload")
        if not isinstance(payload, dict) or set(payload) != CHAT_CONTEXT_PAYLOAD_FIELDS:
            return GateResult.drop("SCHEMA_KEYS_INVALID")

        if payload["explicit_business_confirmation"] is not True:
            return GateResult.drop("BUSINESS_CONFIRMATION_REQUIRED")
        if payload["manager_or_admin_approved"] is not True:
            return GateResult.drop("MANAGER_APPROVAL_REQUIRED")

        shadow_eval_cases = payload["shadow_eval_cases"]
        if type(shadow_eval_cases) is not int or shadow_eval_cases < 100:
            return GateResult.drop("SHADOW_EVAL_CASES_TOO_LOW")
        if payload["pii_zero"] is not True:
            return GateResult.drop("PII_NOT_ZERO")
        if payload["false_learning_zero"] is not True:
            return GateResult.drop("FALSE_LEARNING_NOT_ZERO")
        if not is_sha256(payload["context_digest"]):
            return GateResult.drop("CONTEXT_DIGEST_INVALID")

        return GateResult.accept(candidate)


def validate_chat_context_provenance(candidate: dict[str, Any]) -> str | None:
    verification = candidate.get("verification")
    if not isinstance(verification, dict) or set(verification) != CHAT_CONTEXT_VERIFICATION_FIELDS:
        return "SCHEMA_KEYS_INVALID"

    try:
        validate_verified_by(verification.get("verified_by"))
    except IntegratedLearningError:
        return "VERIFIED_BY_INVALID"

    try:
        validate_verified_at(verification.get("verified_at"))
    except IntegratedLearningError:
        return "VERIFIED_AT_INVALID"

    if not is_sha256(verification.get("evidence_digest")):
        return "EVIDENCE_DIGEST_INVALID"

    try:
        validate_evidence_ref(verification.get("evidence_ref"))
    except IntegratedLearningError:
        return "EVIDENCE_REF_INVALID"

    return None


def validate_chat_context_source_refs(candidate: dict[str, Any]) -> str | None:
    source_refs = candidate.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        return "SOURCE_REF_INVALID"

    has_usage_log = False
    for item in source_refs:
        if not isinstance(item, dict) or set(item) != CHAT_CONTEXT_SOURCE_REF_FIELDS:
            return "SOURCE_REF_INVALID"
        ref_type = item["ref_type"]
        if ref_type not in CHAT_CONTEXT_ALLOWED_SOURCE_TYPES:
            return "SOURCE_REF_INVALID"
        if not is_sha256(item["ref_id_digest"]):
            return "SOURCE_REF_INVALID"
        if ref_type == "usage_log":
            has_usage_log = True

    if not has_usage_log:
        return "SOURCE_REF_INVALID"
    return None
