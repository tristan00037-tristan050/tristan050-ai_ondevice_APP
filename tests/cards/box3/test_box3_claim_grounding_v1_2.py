from __future__ import annotations

from butler_pc_core.cards.box3.claim_grounding import ground_claims
from butler_pc_core.cards.box3.security import sha256_digest


def test_claim_grounding_supported_unsupported_and_non_claim_levels():
    evidence_text = "프로젝트 알파는 내부 검토를 완료했습니다. 담당 조직은 운영팀입니다."
    draft_text = "\n".join(
        [
            "제목: 프로젝트 알파 실행 초안",
            "배경: 프로젝트 알파는 내부 검토를 완료했습니다.",
            "핵심 내용: 담당 조직은 운영팀입니다.",
            "최종 문안: 신규 예산은 확정되었습니다.",
        ]
    )

    verdicts, summary = ground_claims(
        draft_text=draft_text,
        evidence_texts=[evidence_text],
        evidence_digests=[sha256_digest(evidence_text)],
    )

    levels = [item.support_level for item in verdicts]
    assert "non_claim" in levels
    assert levels.count("supported") == 2
    assert levels.count("unsupported") == 1
    assert summary.fail_class == "BLOCK_UNSUPPORTED_CLAIM"
    assert summary.unsupported_claim_rate == 0.3333
    assert all("신규 예산" not in item.to_dict().get("claim_digest", "") for item in verdicts)


def test_claim_grounding_no_evidence_is_needs_review_not_supported():
    draft_text = "배경: 프로젝트 알파는 내부 검토를 완료했습니다."

    verdicts, summary = ground_claims(
        draft_text=draft_text,
        evidence_texts=[],
        evidence_digests=[],
    )

    assert verdicts[0].support_level == "no_evidence"
    assert summary.fail_class == "NEEDS_REVIEW_NO_EVIDENCE_CLAIM"
    assert summary.no_evidence_rate == 1.0
