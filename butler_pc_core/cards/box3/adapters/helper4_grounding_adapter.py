from __future__ import annotations

from ..types import EvidenceUnit, Box3Citation, Box3Grounding


def verify_grounding(
    *,
    citations: list[Box3Citation],
    evidence_units: list[EvidenceUnit],
    injected_unsupported_claim_count: int = 0,
) -> tuple[Box3Grounding, str | None]:
    evidence_digest_set = {unit.unit_digest for unit in evidence_units}
    source_digest_set = {unit.source_digest for unit in evidence_units}
    supported = [
        citation
        for citation in citations
        if citation["evidence_unit_digest"] in evidence_digest_set
        and citation["source_digest"] in source_digest_set
        and citation["support_level"] == "supported"
    ]
    total_units = max(len(evidence_units), 1)
    reference_coverage = len({item["evidence_unit_digest"] for item in supported}) / total_units
    source_digest_coverage = len({item["source_digest"] for item in supported}) / max(len(source_digest_set), 1)
    unsupported_claim_rate = injected_unsupported_claim_count / max(len(citations) + injected_unsupported_claim_count, 1)
    grounding_pass_rate = 1.0 - unsupported_claim_rate
    grounding: Box3Grounding = {
        "reference_coverage": round(reference_coverage, 4),
        "grounding_pass_rate": round(grounding_pass_rate, 4),
        "unsupported_claim_rate": round(unsupported_claim_rate, 4),
        "contradiction_count": 0,
        "source_digest_coverage": round(source_digest_coverage, 4),
    }
    if unsupported_claim_rate > 0.03:
        return grounding, "GROUNDING_UNSUPPORTED_CLAIM_RATE_EXCEEDED"
    if reference_coverage < 0.80:
        return grounding, "GROUNDING_REFERENCE_COVERAGE_LOW"
    if source_digest_coverage < 0.90:
        return grounding, "GROUNDING_SOURCE_DIGEST_COVERAGE_LOW"
    return grounding, None

