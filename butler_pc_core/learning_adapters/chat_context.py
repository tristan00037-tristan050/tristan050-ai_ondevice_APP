from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.learning_core.contracts import (
    GateResult,
    IntegratedLearningError,
    _require_evidence_digest,
    canonical_digest,
    is_sha256,
    validate_evidence_ref,
    validate_evidence_ref_for_test_fixture,
    validate_verified_at,
    validate_verified_by,
)

ALLOWED_RUN_MODE = frozenset({"production", "integration", "fixture_test"})
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
CHAT_CONTEXT_REQUIRED_VERIFICATION_FIELDS = frozenset(
    {"verified_by", "verified_at", "evidence_digest", "evidence_ref"}
)
CHAT_CONTEXT_VERIFICATION_FIELDS = CHAT_CONTEXT_REQUIRED_VERIFICATION_FIELDS | {"evidence_report_sha256"}
CHAT_CONTEXT_DROP_REASONS = frozenset(
    {
        "CHAT_CONTEXT_DISABLED",
        "RUN_MODE_INVALID",
        "FIXTURE_MODE_FORBIDDEN",
        "BUSINESS_CONFIRMATION_REQUIRED",
        "MANAGER_APPROVAL_REQUIRED",
        "SHADOW_EVAL_CASES_TOO_LOW",
        "PII_NOT_ZERO",
        "FALSE_LEARNING_NOT_ZERO",
        "CONTEXT_DIGEST_INVALID",
        "EVIDENCE_DIGEST_INVALID",
        "EVIDENCE_REPORT_BINDING_REQUIRED",
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
    run_mode: str = "production"

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        if self.run_mode not in ALLOWED_RUN_MODE:
            return GateResult.drop("RUN_MODE_INVALID")
        if not self.enabled:
            return GateResult.drop("CHAT_CONTEXT_DISABLED")

        mode_reason = validate_no_run_mode_contamination(candidate)
        if mode_reason is not None:
            return GateResult.drop(mode_reason)

        provenance_reason = validate_chat_context_provenance(candidate, run_mode=self.run_mode)
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


def validate_no_run_mode_contamination(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"run_mode", "fixture_mode"}:
                return "FIXTURE_MODE_FORBIDDEN"
            child_reason = validate_no_run_mode_contamination(child)
            if child_reason is not None:
                return child_reason
    elif isinstance(value, list):
        for child in value:
            child_reason = validate_no_run_mode_contamination(child)
            if child_reason is not None:
                return child_reason
    return None


def validate_chat_context_provenance(candidate: dict[str, Any], *, run_mode: str = "production") -> str | None:
    if run_mode not in ALLOWED_RUN_MODE:
        return "RUN_MODE_INVALID"

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
        if run_mode == "fixture_test":
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

    return validate_evidence_report_binding(
        verification.get("evidence_report_sha256"), evidence_digest=evidence_digest, run_mode=run_mode
    )


def _is_exact_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value


def validate_evidence_report_binding(raw_value: Any, *, evidence_digest: str, run_mode: str) -> str | None:
    if run_mode not in ALLOWED_RUN_MODE:
        return "RUN_MODE_INVALID"
    if raw_value is None:
        if run_mode == "fixture_test":
            return None
        return "EVIDENCE_REPORT_BINDING_REQUIRED"
    if not _is_exact_string(raw_value):
        return "EVIDENCE_REPORT_BINDING_INVALID"
    if not is_sha256(raw_value):
        return "EVIDENCE_REPORT_BINDING_INVALID"
    try:
        if canonical_digest(raw_value) != canonical_digest(evidence_digest):
            return "EVIDENCE_REPORT_BINDING_INVALID"
    except IntegratedLearningError:
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
