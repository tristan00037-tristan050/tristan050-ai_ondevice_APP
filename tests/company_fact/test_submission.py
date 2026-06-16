from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any

import pytest

from butler_pc_core.company_fact.audit import CompanyFactAuditStore
from butler_pc_core.company_fact.storage import CompanyFactStore
from butler_pc_core.company_fact.submission import submit_confirmed_candidate
from butler_pc_core.company_policy.contracts import sha256_text, stable_json_digest


RAW_VALUES = [
    "출장비는 3만원 이하만 영수증으로 정산합니다.",
    "출장비 정산 기준은?",
    "사내규정",
    "policy.xlsx",
    "/Users/private/policy.xlsx",
    "셀값",
]


def _draft(**overrides: Any) -> dict[str, Any]:
    value = {
        "category": "accounting_policy",
        "question_patterns": ["출장비 정산 기준은?", "출장비 정산 기준 알려줘"],
        "keywords_required": [],
        "keywords_any": ["출장비", "정산"],
        "answer_runtime_text": "출장비는 3만원 이하만 영수증으로 정산합니다.",
        "source": "사내규정",
        "source_url": None,
        "source_doc": None,
        "verified_at": "2026-06-16",
        "expires_at": None,
        "confidence": 0.88,
    }
    value.update(overrides)
    return value


@dataclass
class _Entry:
    fact_id: str = "company-fact-test"
    status: str = "CANDIDATE"
    fact_digest: str = sha256_text("fact")


class _SpyStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.approve_called = False

    def save_candidate(self, **payload: Any):
        self.calls.append(payload)
        return _Entry(), {"audit_id": "audit-test"}

    def approve_candidate(self, *_args: Any, **_kwargs: Any):
        self.approve_called = True
        raise AssertionError("APPROVE_SHOULD_NOT_BE_CALLED")


def _assert_raw_free(value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    for raw in RAW_VALUES:
        assert raw not in encoded


def test_confirmed_valid_draft_submits_candidate_once():
    store = _SpyStore()
    draft = _draft()
    outcome = submit_confirmed_candidate(
        draft,
        confirmed=True,
        extraction_draft_digest=sha256_text("extractor-draft"),
        confirmed_draft_digest=stable_json_digest(draft),
        confirmed_by_digest=sha256_text("reviewer"),
        store=store,  # type: ignore[arg-type]
    )

    assert outcome.status == "submitted"
    assert outcome.fact_status == "CANDIDATE"
    assert outcome.fact_digest == sha256_text("fact")
    assert outcome.audit_ref == "audit-test"
    assert len(store.calls) == 1
    assert store.calls[0]["answer_runtime_text"] == draft["answer_runtime_text"]
    assert store.approve_called is False
    assert outcome.auto_approve_zero is True
    assert outcome.resolver_exposure_zero is True


def test_unconfirmed_draft_does_not_call_save_candidate():
    store = _SpyStore()
    draft = _draft()
    outcome = submit_confirmed_candidate(
        draft,
        confirmed=False,
        extraction_draft_digest=sha256_text("extractor-draft"),
        confirmed_draft_digest=stable_json_digest(draft),
        confirmed_by_digest=sha256_text("reviewer"),
        store=store,  # type: ignore[arg-type]
    )

    assert outcome.status == "not_confirmed"
    assert outcome.reason_code == "CONFIRMATION_REQUIRED"
    assert store.calls == []
    assert outcome.fact_id is None


def test_edited_draft_is_revalidated_and_provenance_keeps_both_digests():
    store = _SpyStore()
    original = _draft(answer_runtime_text="원본 답변은 확정 전이라 저장하면 안 됩니다.")
    edited = _draft(answer_runtime_text="출장비는 5만원 이하만 영수증으로 정산합니다.")
    outcome = submit_confirmed_candidate(
        edited,
        confirmed=True,
        extraction_draft_digest=stable_json_digest(original),
        confirmed_draft_digest=stable_json_digest(edited),
        confirmed_by_digest=sha256_text("reviewer"),
        store=store,  # type: ignore[arg-type]
    )

    assert outcome.status == "submitted"
    assert outcome.submission_provenance is not None
    assert outcome.submission_provenance["origin"] == "AUTO_EXTRACTION_CONFIRMED"
    assert outcome.submission_provenance["extraction_draft_digest"] == stable_json_digest(original)
    assert outcome.submission_provenance["confirmed_draft_digest"] == stable_json_digest(edited)
    assert outcome.submission_provenance["confirmed_by_digest"] == sha256_text("reviewer")
    assert outcome.submission_provenance_digest == stable_json_digest(outcome.submission_provenance)


@pytest.mark.parametrize(
    "override",
    [
        {"question_patterns": ["하나뿐인 질문"]},
        {"answer_runtime_text": "짧음"},
        {"source": "ab"},
        {"confidence": 1.0},
    ],
)
def test_invalid_drafts_are_rejected_without_store_call(override: dict[str, Any]):
    store = _SpyStore()
    draft = _draft(**override)
    outcome = submit_confirmed_candidate(
        draft,
        confirmed=True,
        confirmed_draft_digest=stable_json_digest(draft),
        store=store,  # type: ignore[arg-type]
    )

    assert outcome.status == "invalid_draft"
    assert outcome.reason_code == "CANDIDATE_SCHEMA_INVALID"
    assert store.calls == []


def test_confirmed_digest_mismatch_blocks_store_call():
    store = _SpyStore()
    draft = _draft()
    outcome = submit_confirmed_candidate(
        draft,
        confirmed=True,
        confirmed_draft_digest=sha256_text("different-draft"),
        store=store,  # type: ignore[arg-type]
    )

    assert outcome.status == "invalid_draft"
    assert outcome.reason_code == "CONFIRMED_DRAFT_DIGEST_MISMATCH"
    assert store.calls == []


def test_real_store_creates_candidate_only_and_audit_ref(tmp_path):
    store = CompanyFactStore(root=tmp_path)
    draft = _draft()
    outcome = submit_confirmed_candidate(
        draft,
        confirmed=True,
        extraction_draft_digest=sha256_text("extractor-draft"),
        confirmed_draft_digest=stable_json_digest(draft),
        confirmed_by_digest=sha256_text("reviewer"),
        store=store,
    )

    assert outcome.status == "submitted"
    assert outcome.fact_status == "CANDIDATE"
    assert outcome.fact_id is not None
    entry = store.list_index_entries(status="CANDIDATE")[0]
    assert entry.fact_id == outcome.fact_id
    assert store.list_index_entries(status="ACTIVE") == []
    assert outcome.audit_ref


def test_outcome_and_audit_dict_are_field_aware_raw_zero():
    draft = _draft(source_doc="policy.xlsx")
    outcome = submit_confirmed_candidate(
        draft,
        confirmed=False,
        extraction_draft_digest=sha256_text("extractor-draft"),
        confirmed_draft_digest=stable_json_digest(draft),
        confirmed_by_digest=sha256_text("reviewer"),
    )

    assert outcome.raw_text_logged is False
    _assert_raw_free(outcome.to_dict())
    _assert_raw_free(outcome.to_audit_dict())
    assert outcome.to_audit_dict()["confirmed_draft_digest"].startswith("sha256:")


def test_no_approve_resolver_or_active_path_in_submission_source():
    import butler_pc_core.company_fact.submission as submission

    source = inspect.getsource(submission)
    assert "approve_candidate(" not in source
    assert "CompanyKnowledgeResolver" not in source
    assert '"ACTIVE"' not in source
    assert "resolve(" not in source


def test_storage_and_audit_signatures_are_unchanged():
    save_params = inspect.signature(CompanyFactStore.save_candidate).parameters
    audit_params = inspect.signature(CompanyFactAuditStore.append).parameters

    assert list(save_params) == [
        "self",
        "category",
        "question_patterns",
        "keywords_required",
        "keywords_any",
        "answer_runtime_text",
        "source",
        "source_url",
        "source_doc",
        "verified_at",
        "expires_at",
        "confidence",
    ]
    assert list(audit_params) == [
        "self",
        "action",
        "fact_digest",
        "actor_digest",
        "reason_code",
    ]
