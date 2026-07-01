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

PRODUCER_VERSION = "approved_fact_producer.v1.0.0"
TARGET_KIND = "approved_fact"
LEARNING_SOURCE_TYPE = "verified_approved_fact"
PAYLOAD_KEYS = frozenset({"fact_status", "known_bad", "deprecated", "superseded", "fact_digest"})


class ApprovedFactProducerError(ProducerInputError):
    pass


@dataclass(frozen=True)
class ApprovedFactLearningArtifact:
    fact_status: str
    fact_digest: str
    expected_effect_digest: str
    known_bad: bool = False
    deprecated: bool = False
    superseded: bool = False
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)
    verified_by: str = "group_a"
    verified_at: str = DEFAULT_VERIFIED_AT
    evidence_digest: str | None = None
    evidence_ref: str = DIGEST_ONLY_EVIDENCE_REF


def _fail(code: str) -> None:
    raise ApprovedFactProducerError(code)


def coerce_approved_fact_artifact(artifact: ApprovedFactLearningArtifact | Mapping[str, Any]) -> ApprovedFactLearningArtifact:
    data = artifact_to_mapping(artifact, ApprovedFactLearningArtifact)
    ensure_no_forbidden_keys(data)
    ensure_exact_fields(data, ApprovedFactLearningArtifact)
    return ApprovedFactLearningArtifact(
        fact_status=str_field(data, "fact_status", "FACT_STATUS_REQUIRED"),
        fact_digest=str_field(data, "fact_digest", "FACT_DIGEST_REQUIRED"),
        expected_effect_digest=str_field(data, "expected_effect_digest", "EXPECTED_EFFECT_DIGEST_REQUIRED"),
        known_bad=bool_field(data, "known_bad", default=False, error_code="KNOWN_BAD_INVALID"),
        deprecated=bool_field(data, "deprecated", default=False, error_code="DEPRECATED_INVALID"),
        superseded=bool_field(data, "superseded", default=False, error_code="SUPERSEDED_INVALID"),
        source_refs=source_refs_from_mapping(data),
        verified_by=str(data.get("verified_by", "group_a")).strip() or "group_a",
        verified_at=str(data.get("verified_at", DEFAULT_VERIFIED_AT)).strip(),
        evidence_digest=(None if data.get("evidence_digest") is None else str(data.get("evidence_digest")).strip()),
        evidence_ref=str(data.get("evidence_ref", DIGEST_ONLY_EVIDENCE_REF)).strip(),
    )


def build_approved_fact_candidate(artifact: ApprovedFactLearningArtifact | Mapping[str, Any]) -> dict[str, Any]:
    item = coerce_approved_fact_artifact(artifact)
    fact_digest = validate_digest_or_drop(item.fact_digest, "FACT")
    evidence_digest = validate_digest_or_drop(item.evidence_digest or fact_digest, "EVIDENCE")
    source_refs = normalize_source_refs(
        item.source_refs,
        fallback_type="approval",
        fallback_digest=fact_digest,
    )
    payload = {
        "fact_status": item.fact_status,
        "known_bad": item.known_bad,
        "deprecated": item.deprecated,
        "superseded": item.superseded,
        "fact_digest": fact_digest,
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


def ingest_verified_approved_fact(
    artifact: ApprovedFactLearningArtifact | Mapping[str, Any],
    runner: LearningIntakeRunner,
) -> dict[str, Any]:
    try:
        candidate = build_approved_fact_candidate(artifact)
    except ProducerInputError as exc:
        return digest_safe_drop_summary(TARGET_KIND, exc)
    return ingest_candidate(candidate, runner)
