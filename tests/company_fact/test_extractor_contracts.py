from __future__ import annotations

from butler_pc_core.company_fact.extractor import (
    EvidenceUnitRuntime,
    extract_company_fact_candidate,
    sha256_text,
)
from butler_pc_core.company_fact.routes import CompanyFactCandidateRequest


def _unit(text: str, *, kind: str = "qa") -> EvidenceUnitRuntime:
    return EvidenceUnitRuntime(
        unit_id="u1",
        text_runtime_only=text,
        source_digest=sha256_text("source"),
        unit_digest=sha256_text(text),
        unit_kind=kind,  # type: ignore[arg-type]
        order=0,
    )


def test_groundable_qa_returns_pydantic_valid_candidate_draft():
    text = (
        "Q: 출장비 정산 기준은?\n"
        "A: 출장비는 3만원 이하만 영수증으로 정산합니다.\n"
        "출처: 사내규정\n"
        "시행일: 2026년 6월 16일\n"
    )
    outcome = extract_company_fact_candidate(
        {"primary_destination": "company_fact_candidate"},
        {"feature_set_digest": sha256_text("feature")},
        "회사 규정",
        evidence_units_runtime_only=[_unit(text)],
    )

    assert outcome.status == "draft_ready"
    assert outcome.reason_code == "DRAFT_READY"
    assert outcome.candidate_draft is not None
    candidate = CompanyFactCandidateRequest(**outcome.candidate_draft)
    assert candidate.confidence < 1.0
    assert len(candidate.question_patterns) >= 2
    assert candidate.verified_at == "2026-06-16"


def test_source_missing_needs_confirmation_without_candidate_draft():
    text = (
        "Q: 출장비 정산 기준은?\n"
        "A: 출장비는 3만원 이하만 영수증으로 정산합니다.\n"
    )
    outcome = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=[_unit(text)])

    assert outcome.status == "needs_confirmation"
    assert outcome.candidate_draft is None
    assert "source" in outcome.missing_fields
    assert "SOURCE_REQUIRED" in outcome.reason_code


def test_confidence_never_reaches_one_for_candidate_draft():
    text = (
        "Q: 보안 비밀번호 기준은?\n"
        "A: 비밀번호는 90일마다 변경해야 합니다.\n"
        "출처: 보안정책\n"
    )
    outcome = extract_company_fact_candidate({}, {}, "보안 규정", evidence_units_runtime_only=[_unit(text)])

    assert outcome.status == "draft_ready"
    assert outcome.candidate_draft is not None
    assert outcome.candidate_draft["confidence"] < 1.0
    assert outcome.approve_called_zero is True
    assert outcome.auto_submit_zero is True


def test_invalid_date_is_left_empty_not_raw_preserved():
    text = (
        "Q: 출장비 정산 기준은?\n"
        "A: 출장비는 3만원 이하만 영수증으로 정산합니다.\n"
        "출처: 사내규정\n"
        "시행일: 곧 시행\n"
    )
    outcome = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=[_unit(text)])

    assert outcome.status == "draft_ready"
    assert outcome.candidate_draft is not None
    assert outcome.candidate_draft["verified_at"] is None
    assert "곧 시행" not in str(outcome.candidate_draft)


def test_multi_qa_uses_only_question_paired_with_selected_answer():
    text = (
        "Q: 출장비 정산 기준은?\n"
        "A: 출장비는 3만원 이하만 영수증으로 정산합니다.\n"
        "Q: 보안 비밀번호 기준은?\n"
        "A: 비밀번호는 90일마다 변경해야 합니다.\n"
        "출처: 사내규정\n"
    )
    outcome = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=[_unit(text)])

    assert outcome.status == "draft_ready"
    assert outcome.candidate_draft is not None
    assert outcome.candidate_draft["answer_runtime_text"] == "출장비는 3만원 이하만 영수증으로 정산합니다."
    assert "출장비 정산 기준은?" in outcome.candidate_draft["question_patterns"]
    assert "보안 비밀번호 기준은?" not in outcome.candidate_draft["question_patterns"]


def test_label_priority_is_deterministic_for_source_and_source_doc():
    text = (
        "Q: 출장비 정산 기준은?\n"
        "A: 출장비는 3만원 이하만 영수증으로 정산합니다.\n"
        "문서명: 보조문서\n"
        "출처: 우선출처\n"
        "source: 영문출처\n"
        "시행일: 2026/06/16\n"
    )
    first = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=[_unit(text)])
    second = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=[_unit(text)])

    assert first.status == "draft_ready"
    assert second.status == "draft_ready"
    assert first.candidate_draft is not None
    assert second.candidate_draft is not None
    assert first.candidate_draft["source"] == "우선출처"
    assert first.candidate_draft["source_doc"] == "보조문서"
    assert first.draft_digest == second.draft_digest
