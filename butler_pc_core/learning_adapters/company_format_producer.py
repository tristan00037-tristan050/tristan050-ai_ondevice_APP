from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from butler_pc_core.learning_core.runner import LearningIntakeRunner

from .producer_common import (
    DEFAULT_VERIFIED_AT,
    DIGEST_ONLY_EVIDENCE_REF,
    ProducerInputError,
    artifact_to_mapping,
    build_candidate_envelope,
    digest_safe_drop_summary,
    ensure_exact_fields,
    ensure_no_forbidden_keys,
    ingest_candidate,
    normalize_source_refs,
    source_refs_from_mapping,
    stable_digest_text,
    str_field,
    validate_digest_or_drop,
    validate_ref_or_drop,
)

PRODUCER_VERSION = "company_format_producer.v1.0.0"
TARGET_KIND = "company_format"
LEARNING_SOURCE_TYPE = "verified_company_format"
PAYLOAD_KEYS = frozenset({"format_ref", "template_digest", "format_status"})


class CompanyFormatProducerError(ProducerInputError):
    pass


@dataclass(frozen=True)
class CompanyFormatLearningArtifact:
    format_ref: str
    template_digest: str
    format_status: str
    expected_effect_digest: str
    source_refs: tuple[dict[str, str], ...] = field(default_factory=tuple)
    verified_by: str = "group_a"
    verified_at: str = DEFAULT_VERIFIED_AT
    evidence_digest: str | None = None
    evidence_ref: str = DIGEST_ONLY_EVIDENCE_REF


def _fail(code: str) -> None:
    raise CompanyFormatProducerError(code)


def coerce_company_format_artifact(artifact: CompanyFormatLearningArtifact | Mapping[str, Any]) -> CompanyFormatLearningArtifact:
    data = artifact_to_mapping(artifact, CompanyFormatLearningArtifact)
    ensure_no_forbidden_keys(data)
    ensure_exact_fields(data, CompanyFormatLearningArtifact)
    return CompanyFormatLearningArtifact(
        format_ref=str_field(data, "format_ref", "FORMAT_REF_REQUIRED"),
        template_digest=str_field(data, "template_digest", "TEMPLATE_DIGEST_REQUIRED"),
        format_status=str_field(data, "format_status", "FORMAT_STATUS_REQUIRED"),
        expected_effect_digest=str_field(data, "expected_effect_digest", "EXPECTED_EFFECT_DIGEST_REQUIRED"),
        source_refs=source_refs_from_mapping(data),
        verified_by=str(data.get("verified_by", "group_a")).strip() or "group_a",
        verified_at=str(data.get("verified_at", DEFAULT_VERIFIED_AT)).strip(),
        evidence_digest=(None if data.get("evidence_digest") is None else str(data.get("evidence_digest")).strip()),
        evidence_ref=str(data.get("evidence_ref", DIGEST_ONLY_EVIDENCE_REF)).strip(),
    )


def build_company_format_candidate(artifact: CompanyFormatLearningArtifact | Mapping[str, Any]) -> dict[str, Any]:
    item = coerce_company_format_artifact(artifact)
    format_ref = validate_ref_or_drop(item.format_ref, "FORMAT_REF")
    template_digest = validate_digest_or_drop(item.template_digest, "TEMPLATE")
    evidence_digest = validate_digest_or_drop(item.evidence_digest or template_digest, "EVIDENCE")
    source_refs = normalize_source_refs(
        item.source_refs,
        fallback_type="format",
        fallback_digest=stable_digest_text("format_ref:" + format_ref),
    )
    payload = {
        "format_ref": format_ref,
        "template_digest": template_digest,
        "format_status": item.format_status,
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


def ingest_verified_company_format(
    artifact: CompanyFormatLearningArtifact | Mapping[str, Any],
    runner: LearningIntakeRunner,
) -> dict[str, Any]:
    try:
        candidate = build_company_format_candidate(artifact)
    except ProducerInputError as exc:
        return digest_safe_drop_summary(TARGET_KIND, exc)
    return ingest_candidate(candidate, runner)
