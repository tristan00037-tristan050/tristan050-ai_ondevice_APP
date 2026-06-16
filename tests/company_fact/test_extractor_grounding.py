from __future__ import annotations

from butler_pc_core.company_fact.extractor import (
    EvidenceUnitRuntime,
    extract_company_fact_candidate,
    sha256_text,
)


def _unit(text: str, *, kind: str = "paragraph") -> EvidenceUnitRuntime:
    return EvidenceUnitRuntime(
        unit_id="u1",
        text_runtime_only=text,
        source_digest=sha256_text("source"),
        unit_digest=sha256_text(text),
        unit_kind=kind,  # type: ignore[arg-type]
        order=0,
    )


def test_label_value_with_source_is_grounded_and_category_inferred():
    text = "경비 정산 기준: 3만원 이하 영수증 제출\n출처: 회계규정\n시행일: 2026-06-16"
    outcome = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=[_unit(text, kind="label_value")])

    assert outcome.status == "draft_ready"
    assert outcome.candidate_draft is not None
    assert outcome.candidate_draft["answer_runtime_text"] == "3만원 이하 영수증 제출"
    assert outcome.candidate_draft["category"] == "accounting_policy"
    assert outcome.candidate_draft["verified_at"] == "2026-06-16"


def test_ungroundable_request_abstains_without_fabricating_fact():
    outcome = extract_company_fact_candidate(
        {},
        {},
        "회사 규정을 요약해서 fact로 만들어줘",
        source_text_runtime_only="이 문서는 일반 안내문입니다. 구체 규정이나 출처가 없습니다.",
    )

    assert outcome.status == "abstain"
    assert outcome.candidate_draft is None
    assert outcome.reason_code == "UNSUPPORTED_INPUT_SURFACE"
    assert outcome.draft_digest is None


def test_no_grounding_text_abstains():
    outcome = extract_company_fact_candidate({}, {}, "회사 규정")

    assert outcome.status == "abstain"
    assert outcome.reason_code == "NO_GROUNDING_TEXT"
    assert outcome.candidate_draft is None


def test_paragraph_fact_requires_answer_to_remain_in_evidence():
    text = "휴가 신청 기준은 부서장 승인 후 인사팀에 제출하는 절차입니다.\n출처: 인사규정"
    outcome = extract_company_fact_candidate({}, {}, "휴가 규정", source_text_runtime_only=text)

    assert outcome.status == "draft_ready"
    assert outcome.candidate_draft is not None
    assert outcome.candidate_draft["answer_runtime_text"] in text
    assert outcome.candidate_draft["category"] == "hr_policy"
