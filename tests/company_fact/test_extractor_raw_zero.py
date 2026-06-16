from __future__ import annotations

import json

from butler_pc_core.company_fact.extractor import (
    EvidenceUnitRuntime,
    extract_company_fact_candidate,
    sha256_text,
)


FORBIDDEN_RAW = [
    "출장비는 3만원 이하만 영수증으로 정산합니다.",
    "사내규정",
    "/Users/private/company-policy.txt",
    "alice@example.com",
    "sk-proj-secret-like-token",
    "1234567890",
]


def _unit(text: str) -> EvidenceUnitRuntime:
    return EvidenceUnitRuntime(
        unit_id="u1",
        text_runtime_only=text,
        source_digest=sha256_text("source"),
        unit_digest=sha256_text(text),
        unit_kind="qa",
        order=0,
    )


def _assert_raw_free(value: dict) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for raw in FORBIDDEN_RAW:
        assert raw not in encoded


def test_audit_dict_excludes_candidate_answer_source_and_runtime_text():
    text = (
        "Q: 출장비 정산 기준은?\n"
        "A: 출장비는 3만원 이하만 영수증으로 정산합니다.\n"
        "출처: 사내규정\n"
    )
    outcome = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=[_unit(text)])

    assert outcome.status == "draft_ready"
    assert outcome.candidate_draft is not None
    _assert_raw_free(outcome.to_audit_dict())
    assert outcome.to_audit_dict()["draft_digest"].startswith("sha256:")
    assert outcome.to_audit_dict()["raw_text_logged"] is False


def test_dlp_blocks_email_secret_account_and_path_without_raw_in_audit_dict():
    raw = "/Users/private/company-policy.txt alice@example.com sk-proj-secret-like-token 1234567890"
    outcome = extract_company_fact_candidate({}, {}, "회사 규정", source_text_runtime_only=raw)

    assert outcome.status == "abstain"
    assert outcome.reason_code == "DLP_OR_SECRET_BLOCKED"
    assert outcome.candidate_draft is None
    _assert_raw_free(outcome.to_audit_dict())


def test_evidence_limit_exceeded_abstains_without_truncation():
    too_many = [
        EvidenceUnitRuntime(
            unit_id=f"u{idx}",
            text_runtime_only=f"근거 {idx}",
            source_digest=sha256_text("source"),
            unit_digest=sha256_text(f"근거 {idx}"),
            unit_kind="paragraph",
            order=idx,
        )
        for idx in range(51)
    ]
    outcome = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=too_many)

    assert outcome.status == "abstain"
    assert outcome.reason_code == "EVIDENCE_LIMIT_EXCEEDED"
    assert len(outcome.evidence_digests) == 51


def test_single_evidence_unit_limit_exceeded_abstains():
    text = "가" * 4001
    outcome = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=[_unit(text)])

    assert outcome.status == "abstain"
    assert outcome.reason_code == "EVIDENCE_LIMIT_EXCEEDED"


def test_total_evidence_limit_exceeded_abstains():
    units = [
        EvidenceUnitRuntime(
            unit_id=f"u{idx}",
            text_runtime_only="가" * 2000,
            source_digest=sha256_text("source"),
            unit_digest=sha256_text(str(idx)),
            unit_kind="paragraph",
            order=idx,
        )
        for idx in range(33)
    ]
    outcome = extract_company_fact_candidate({}, {}, "회사 규정", evidence_units_runtime_only=units)

    assert outcome.status == "abstain"
    assert outcome.reason_code == "EVIDENCE_LIMIT_EXCEEDED"
