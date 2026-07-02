from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.learning_core.contracts import (
    GateResult,
    IntegratedLearningError,
    _require_evidence_digest,
    is_sha256,
    validate_evidence_ref,
    validate_evidence_ref_for_test_fixture,
    validate_verified_at,
    validate_verified_by,
)

CHAT_CONTEXT_BASE_PAYLOAD_FIELDS = frozenset(
    {
        "explicit_business_confirmation",
        "manager_or_admin_approved",
        "shadow_eval_cases",
        "pii_zero",
        "false_learning_zero",
        "context_digest",
    }
)
CHAT_CONTEXT_PAYLOAD_FIELDS = CHAT_CONTEXT_BASE_PAYLOAD_FIELDS | {"shadow_eval"}
CHAT_CONTEXT_SHADOW_EVAL_FIELDS = frozenset({"evidence_report_sha256"})
CHAT_CONTEXT_SOURCE_REF_FIELDS = frozenset({"ref_type", "ref_id_digest"})
CHAT_CONTEXT_ALLOWED_SOURCE_TYPES = frozenset({"usage_log", "approval"})
CHAT_CONTEXT_VERIFICATION_FIELDS = frozenset(
    {"verified_by", "verified_at", "evidence_digest", "evidence_ref"}
)
CHAT_CONTEXT_DROP_REASONS = frozenset(
    {
        "CHAT_CONTEXT_DISABLED",
        "BUSINESS_CONFIRMATION_REQUIRED",
        "MANAGER_APPROVAL_REQUIRED",
        "SHADOW_EVAL_CASES_TOO_LOW",
        "PII_NOT_ZERO",
        "FALSE_LEARNING_NOT_ZERO",
        "CONTEXT_DIGEST_INVALID",
        "EVIDENCE_DIGEST_INVALID",
        "EVIDENCE_REPORT_BINDING_INVALID",
        "VERIFIED_BY_INVALID",
        "VERIFIED_AT_INVALID",
        "EVIDENCE_REF_INVALID",
        "SOURCE_REF_INVALID",
        "SCHEMA_KEYS_INVALID",
    }
)


@dataclass(frozen=True)
class ChatContextAdapter:
    target_kind: str = "chat_context"
    enabled: bool = False
    fixture_mode: bool = True

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        if not self.enabled:
            return GateResult.drop("CHAT_CONTEXT_DISABLED")

        provenance_reason = validate_chat_context_provenance(candidate, fixture_mode=self.fixture_mode)
        if provenance_reason is not None:
            return GateResult.drop(provenance_reason)

        source_ref_reason = validate_chat_context_source_refs(candidate)
        if source_ref_reason is not None:
            return GateResult.drop(source_ref_reason)

        payload = candidate.get("payload")
        if not isinstance(payload, dict) or not _has_exact_chat_payload_keys(payload):
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


def _has_exact_chat_payload_keys(payload: dict[str, Any]) -> bool:
    keys = set(payload)
    if keys == CHAT_CONTEXT_BASE_PAYLOAD_FIELDS:
        return True
    if keys == CHAT_CONTEXT_PAYLOAD_FIELDS:
        shadow_eval = payload.get("shadow_eval")
        return isinstance(shadow_eval, dict) and set(shadow_eval) == CHAT_CONTEXT_SHADOW_EVAL_FIELDS
    return False


def validate_chat_context_provenance(candidate: dict[str, Any], *, fixture_mode: bool = True) -> str | None:
    verification = candidate.get("verification")
    if not isinstance(verification, dict):
        return "SCHEMA_KEYS_INVALID"
    unknown = set(verification) - CHAT_CONTEXT_VERIFICATION_FIELDS
    if unknown:
        return "SCHEMA_KEYS_INVALID"
    if "verified_by" not in verification:
        return "VERIFIED_BY_INVALID"
    if "verified_at" not in verification:
        return "VERIFIED_AT_INVALID"
    if "evidence_ref" not in verification:
        return "EVIDENCE_REF_INVALID"
    if "evidence_digest" not in verification:
        return "EVIDENCE_DIGEST_INVALID"

    if not _is_exact_string(verification["verified_by"]):
        return "VERIFIED_BY_INVALID"
    try:
        validate_verified_by(verification["verified_by"])
    except IntegratedLearningError:
        return "VERIFIED_BY_INVALID"

    if not _is_exact_string(verification["verified_at"]):
        return "VERIFIED_AT_INVALID"
    try:
        validate_verified_at(verification["verified_at"])
    except IntegratedLearningError:
        return "VERIFIED_AT_INVALID"

    if not _is_exact_string(verification["evidence_ref"]):
        return "EVIDENCE_REF_INVALID"
    try:
        if fixture_mode:
            validate_evidence_ref_for_test_fixture(verification["evidence_ref"])
        else:
            validate_evidence_ref(verification["evidence_ref"])
    except IntegratedLearningError:
        return "EVIDENCE_REF_INVALID"

    payload = candidate.get("payload")
    if not isinstance(payload, dict) or "context_digest" not in payload:
        return "CONTEXT_DIGEST_INVALID"
    context_digest = payload["context_digest"]
    if not is_sha256(context_digest):
        return "CONTEXT_DIGEST_INVALID"

    try:
        evidence_digest = _require_evidence_digest(
            verification["evidence_digest"], context_digest=context_digest
        )
    except (KeyError, IntegratedLearningError):
        return "EVIDENCE_DIGEST_INVALID"

    shadow_eval_reason = validate_shadow_eval_evidence_report_binding(payload, evidence_digest=evidence_digest)
    if shadow_eval_reason is not None:
        return shadow_eval_reason

    return None


def _is_exact_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value


def validate_shadow_eval_evidence_report_binding(payload: dict[str, Any], *, evidence_digest: str) -> str | None:
    if "shadow_eval" not in payload:
        return None
    shadow_eval = payload["shadow_eval"]
    if not isinstance(shadow_eval, dict) or set(shadow_eval) != CHAT_CONTEXT_SHADOW_EVAL_FIELDS:
        return "SCHEMA_KEYS_INVALID"
    evidence_report_sha256 = shadow_eval["evidence_report_sha256"]
    if not isinstance(evidence_report_sha256, str) or not is_sha256(evidence_report_sha256):
        return "EVIDENCE_REPORT_BINDING_INVALID"
    if evidence_report_sha256 != evidence_digest:
        return "EVIDENCE_REPORT_BINDING_INVALID"
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
