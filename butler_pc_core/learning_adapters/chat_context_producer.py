from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from butler_pc_core.learning_core.runner import LearningIntakeRunner

from .producer_common import (
    DEFAULT_VERIFIED_AT,
    DIGEST_ONLY_EVIDENCE_REF,
    ProducerInputError,
    artifact_to_mapping,
    bool_field,
    build_candidate_envelope,
    digest_safe_drop_summary,
    ensure_exact_fields,
    ensure_no_forbidden_keys,
    ingest_candidate,
    int_field,
    normalize_source_refs,
    source_refs_from_mapping,
    validate_digest_or_drop,
)

PRODUCER_VERSION = "chat_context_producer.v1.0.0"
TARGET_KIND = "chat_context"
LEARNING_SOURCE_TYPE = "verified_chat_context"
PAYLOAD_KEYS = frozenset(
    {
        "explicit_business_confirmation",
        "manager_or_admin_approved",
        "shadow_eval_cases",
        "pii_zero",
        "false_learning_zero",
        "context_digest",
    }
)
ALLOWED_SOURCE_REF_TYPES = frozenset({"usage_log", "approval"})


class ChatContextProducerError(ProducerInputError):
    pass


@dataclass(frozen=True)
class ChatContextLearningArtifact:
    explicit_business_confirmation: bool
    manager_or_admin_approved: bool
    shadow_eval_cases: int
    pii_zero: bool
    false_learning_zero: bool
    context_digest: str
    expected_effect_digest: str
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)
    verified_by: str = "group_a"
    verified_at: str = DEFAULT_VERIFIED_AT
    evidence_digest: str | None = None
    evidence_ref: str = DIGEST_ONLY_EVIDENCE_REF


def _fail(code: str) -> None:
    raise ChatContextProducerError(code)


def _restricted_source_refs(raw_refs: tuple[dict[str, str], ...], *, fallback_digest: str) -> tuple[dict[str, str], ...]:
    if raw_refs:
        for ref in raw_refs:
            if str(ref.get("ref_type", "")).strip() not in ALLOWED_SOURCE_REF_TYPES:
                _fail("SOURCE_REF_TYPE_INVALID")
    try:
        return normalize_source_refs(raw_refs, fallback_type="usage_log", fallback_digest=fallback_digest)
    except ProducerInputError as exc:
        _fail(str(exc))


def coerce_chat_context_artifact(
    artifact: ChatContextLearningArtifact | Mapping[str, Any],
) -> ChatContextLearningArtifact:
    data = artifact_to_mapping(artifact, ChatContextLearningArtifact)
    try:
        ensure_no_forbidden_keys(data)
        ensure_exact_fields(data, ChatContextLearningArtifact)
        return ChatContextLearningArtifact(
            explicit_business_confirmation=bool_field(
                data,
                "explicit_business_confirmation",
                default=False,
                error_code="EXPLICIT_BUSINESS_CONFIRMATION_INVALID",
            ),
            manager_or_admin_approved=bool_field(
                data,
                "manager_or_admin_approved",
                default=False,
                error_code="MANAGER_OR_ADMIN_APPROVED_INVALID",
            ),
            shadow_eval_cases=int_field(data, "shadow_eval_cases", "SHADOW_EVAL_CASES_INVALID"),
            pii_zero=bool_field(data, "pii_zero", default=False, error_code="PII_ZERO_INVALID"),
            false_learning_zero=bool_field(
                data,
                "false_learning_zero",
                default=False,
                error_code="FALSE_LEARNING_ZERO_INVALID",
            ),
            context_digest=str(data.get("context_digest", "")).strip(),
            expected_effect_digest=str(data.get("expected_effect_digest", "")).strip(),
            source_refs=source_refs_from_mapping(data),
            verified_by=str(data.get("verified_by", "group_a")).strip() or "group_a",
            verified_at=str(data.get("verified_at", DEFAULT_VERIFIED_AT)).strip(),
            evidence_digest=(None if data.get("evidence_digest") is None else str(data.get("evidence_digest")).strip()),
            evidence_ref=str(data.get("evidence_ref", DIGEST_ONLY_EVIDENCE_REF)).strip(),
        )
    except KeyError:
        _fail("ARTIFACT_FIELD_REQUIRED")
    except ProducerInputError as exc:
        _fail(str(exc))


def build_chat_context_candidate(artifact: ChatContextLearningArtifact | Mapping[str, Any]) -> dict[str, Any]:
    item = coerce_chat_context_artifact(artifact)
    context_digest = validate_digest_or_drop(item.context_digest, "CHAT_CONTEXT")
    expected_effect_digest = validate_digest_or_drop(item.expected_effect_digest, "EXPECTED_EFFECT")
    evidence_digest = validate_digest_or_drop(item.evidence_digest or context_digest, "EVIDENCE")
    source_refs = _restricted_source_refs(item.source_refs, fallback_digest=context_digest)
    payload = {
        "explicit_business_confirmation": item.explicit_business_confirmation,
        "manager_or_admin_approved": item.manager_or_admin_approved,
        "shadow_eval_cases": item.shadow_eval_cases,
        "pii_zero": item.pii_zero,
        "false_learning_zero": item.false_learning_zero,
        "context_digest": context_digest,
    }
    if set(payload) != PAYLOAD_KEYS:
        _fail("PAYLOAD_KEYS_INVALID")
    try:
        return build_candidate_envelope(
            target_kind=TARGET_KIND,
            adapter_version=PRODUCER_VERSION,
            learning_source_type=LEARNING_SOURCE_TYPE,
            payload=payload,
            expected_effect_digest=expected_effect_digest,
            evidence_digest=evidence_digest,
            evidence_ref=item.evidence_ref,
            source_refs=source_refs,
            verified_by=item.verified_by,
            verified_at=item.verified_at,
        )
    except ProducerInputError as exc:
        _fail(str(exc))


def ingest_verified_chat_context(
    artifact: ChatContextLearningArtifact | Mapping[str, Any],
    runner: LearningIntakeRunner,
) -> dict[str, Any]:
    try:
        candidate = build_chat_context_candidate(artifact)
    except ProducerInputError as exc:
        return digest_safe_drop_summary(TARGET_KIND, exc)
    return ingest_candidate(candidate, runner)
