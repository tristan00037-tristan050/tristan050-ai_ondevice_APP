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
    # Codex P2 정정 (2026-06-01, PR #770): CONTRACT_ONLY 스코프에서 citation 은 digest_linked
    # (검증 없는 digest 연결)이며, 여기서 산출되는 reference/source coverage 는 'digest-link coverage'
    # 를 의미한다(claim-level supported/unsupported 실판정 = real 단계 후속). digest_linked 를
    # supported 와 동일하게 digest-link coverage 에 포함한다 — citation label 과대주장은 제거하되
    # coverage 계산은 보존.
    supported = [
        citation
        for citation in citations
        if citation["evidence_unit_digest"] in evidence_digest_set
        and citation["source_digest"] in source_digest_set
        and citation["support_level"] in ("supported", "digest_linked")
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

