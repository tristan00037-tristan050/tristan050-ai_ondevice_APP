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
    normalize_source_refs,
    source_refs_from_mapping,
    str_field,
    validate_digest_or_drop,
)

PRODUCER_VERSION = "policy_rule_producer.v1.0.0"
TARGET_KIND = "policy_rule"
LEARNING_SOURCE_TYPE = "verified_policy_rule"
PAYLOAD_KEYS = frozenset({"policy_status", "active_policy_digest", "deny_to_allow_auto"})


class PolicyRuleProducerError(ProducerInputError):
    pass


@dataclass(frozen=True)
class PolicyRuleLearningArtifact:
    policy_status: str
    active_policy_digest: str
    expected_effect_digest: str
    deny_to_allow_auto: bool = False
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)
    verified_by: str = "group_a"
    verified_at: str = DEFAULT_VERIFIED_AT
    evidence_digest: str | None = None
    evidence_ref: str = DIGEST_ONLY_EVIDENCE_REF


def _fail(code: str) -> None:
    raise PolicyRuleProducerError(code)


def coerce_policy_rule_artifact(artifact: PolicyRuleLearningArtifact | Mapping[str, Any]) -> PolicyRuleLearningArtifact:
    data = artifact_to_mapping(artifact, PolicyRuleLearningArtifact)
    ensure_no_forbidden_keys(data)
    ensure_exact_fields(data, PolicyRuleLearningArtifact)
    try:
        return PolicyRuleLearningArtifact(
            policy_status=str_field(data, "policy_status", "POLICY_STATUS_REQUIRED"),
            active_policy_digest=str_field(data, "active_policy_digest", "ACTIVE_POLICY_DIGEST_REQUIRED"),
            expected_effect_digest=str_field(data, "expected_effect_digest", "EXPECTED_EFFECT_DIGEST_REQUIRED"),
            deny_to_allow_auto=bool_field(
                data,
                "deny_to_allow_auto",
                default=False,
                error_code="DENY_TO_ALLOW_AUTO_INVALID",
            ),
            source_refs=source_refs_from_mapping(data),
            verified_by=str(data.get("verified_by", "group_a")).strip() or "group_a",
            verified_at=str(data.get("verified_at", DEFAULT_VERIFIED_AT)).strip(),
            evidence_digest=(None if data.get("evidence_digest") is None else str(data.get("evidence_digest")).strip()),
            evidence_ref=str(data.get("evidence_ref", DIGEST_ONLY_EVIDENCE_REF)).strip(),
        )
    except KeyError:
        _fail("ARTIFACT_FIELD_REQUIRED")


def build_policy_rule_candidate(artifact: PolicyRuleLearningArtifact | Mapping[str, Any]) -> dict[str, Any]:
    item = coerce_policy_rule_artifact(artifact)
    active_policy_digest = validate_digest_or_drop(item.active_policy_digest, "ACTIVE_POLICY")
    evidence_digest = validate_digest_or_drop(item.evidence_digest or active_policy_digest, "EVIDENCE")
    source_refs = normalize_source_refs(
        item.source_refs,
        fallback_type="policy",
        fallback_digest=active_policy_digest,
    )
    payload = {
        "policy_status": item.policy_status,
        "active_policy_digest": active_policy_digest,
        "deny_to_allow_auto": item.deny_to_allow_auto,
    }
    if set(payload) != PAYLOAD_KEYS:
        _fail("PAYLOAD_KEYS_INVALID")
    return build_candidate_envelope(
        target_kind=TARGET_KIND,
        adapter_version=PRODUCER_VERSION,
        learning_source_type=LEARNING_SOURCE_TYPE,
        payload=payload,
        expected_effect_digest=item.expected_effect_digest,
        evidence_digest=evidence_digest,
        evidence_ref=item.evidence_ref,
        source_refs=source_refs,
        verified_by=item.verified_by,
        verified_at=item.verified_at,
    )


def ingest_verified_policy_rule(
    artifact: PolicyRuleLearningArtifact | Mapping[str, Any],
    runner: LearningIntakeRunner,
) -> dict[str, Any]:
    try:
        candidate = build_policy_rule_candidate(artifact)
    except ProducerInputError as exc:
        return digest_safe_drop_summary(TARGET_KIND, exc)
    return ingest_candidate(candidate, runner)
