from __future__ import annotations

import pytest

from butler_pc_core.company_fact.contracts import CompanyFactContractError, make_company_fact_record
from butler_pc_core.company_policy.contracts import sha256_text


def _fact_kwargs():
    return {
        "category": "company_policy",
        "question_patterns": ["우리 회사 출장 규정은?", "출장비 규정 알려줘"],
        "keywords_required": ["출장"],
        "keywords_any": ["규정", "출장비"],
        "answer_runtime_text": "출장비는 승인된 사내 규정에 따라 정산합니다.",
        "source": "company_admin_verified",
        "source_doc": "policy-ref-001",
        "confidence": 0.6,
    }


def test_candidate_confidence_must_stay_below_one():
    record = make_company_fact_record(status="CANDIDATE", **_fact_kwargs())

    assert record.status == "CANDIDATE"
    assert record.confidence < 1.0
    with pytest.raises(CompanyFactContractError, match="CANDIDATE_CONFIDENCE"):
        make_company_fact_record(status="CANDIDATE", **{**_fact_kwargs(), "confidence": 1.0})


def test_active_requires_approval_digest_and_confidence_one():
    with pytest.raises(CompanyFactContractError, match="ACTIVE_APPROVAL_REQUIRED"):
        make_company_fact_record(status="ACTIVE", **{**_fact_kwargs(), "confidence": 1.0})
    with pytest.raises(CompanyFactContractError, match="ACTIVE_CONFIDENCE"):
        make_company_fact_record(
            status="ACTIVE",
            **{
                **_fact_kwargs(),
                "confidence": 0.99,
                "approved_by_digest": sha256_text("admin"),
                "approved_at": "2026-06-14T00:00:00Z",
            },
        )

    active = make_company_fact_record(
        status="ACTIVE",
        **{
            **_fact_kwargs(),
            "confidence": 1.0,
            "approved_by_digest": sha256_text("admin"),
            "approved_at": "2026-06-14T00:00:00Z",
        },
    )

    assert active.status == "ACTIVE"
    assert active.confidence == 1.0
    assert active.approved_by_digest == sha256_text("admin")
