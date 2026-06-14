from __future__ import annotations

import json

import pytest

from butler_pc_core.company_fact.audit import GLOBAL_COMPANY_FACT_AUDIT_STORE
from butler_pc_core.company_fact.storage import CompanyFactLoadError, CompanyFactStore
from butler_pc_core.company_policy.admin_auth import AdminAuthError
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text


ANSWER_SENTINEL = "회사 승인 사실 본문은 암호화 vault 안에서만 복호화됩니다."
SOURCE_SENTINEL = "company-source-ref-private"


def _admin(role: str = "admin") -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text(f"company-fact-{role}"),
        role=role,  # type: ignore[arg-type]
        admin_session_digest=sha256_text("company-fact-session"),
        auth_method="test_only",
    )


def _candidate(store: CompanyFactStore):
    return store.save_candidate(
        category="company_rules",
        question_patterns=["우리 회사 지출 결재 기준은?", "지출 결재 규정 알려줘"],
        keywords_required=["지출"],
        keywords_any=["결재", "규정"],
        answer_runtime_text=ANSWER_SENTINEL,
        source=SOURCE_SENTINEL,
        source_doc="policy-ref-001",
        confidence=0.5,
    )


def test_candidate_is_encrypted_and_index_is_digest_only(tmp_path):
    GLOBAL_COMPANY_FACT_AUDIT_STORE.clear()
    store = CompanyFactStore(root=tmp_path / "facts")

    entry, audit = _candidate(store)
    index_text = store.index_path.read_text(encoding="utf-8")
    audit_text = json.dumps(audit, ensure_ascii=False, sort_keys=True)

    assert entry.status == "CANDIDATE"
    assert entry.confidence < 1.0
    assert ANSWER_SENTINEL not in index_text
    assert SOURCE_SENTINEL not in index_text
    assert ANSWER_SENTINEL not in audit_text
    assert SOURCE_SENTINEL not in audit_text
    assert entry.field_digests["answer"] == sha256_text(ANSWER_SENTINEL)
    assert audit["raw_text_logged"] is False
    assert audit["external_send_zero"] is True

    loaded = store.load_fact(entry.fact_id)
    assert loaded.answer_runtime_text == ANSWER_SENTINEL
    assert loaded.source == SOURCE_SENTINEL


def test_candidate_not_listed_as_active_until_admin_approval(tmp_path):
    store = CompanyFactStore(root=tmp_path / "facts")

    entry, _audit = _candidate(store)

    assert store.load_active_facts() == []
    approved, _approve_audit = store.approve_candidate(entry.fact_id, _admin())
    active = store.load_fact(entry.fact_id)

    assert approved.status == "ACTIVE"
    assert active.status == "ACTIVE"
    assert active.confidence == 1.0
    assert active.approved_by_digest == _admin().admin_id_digest
    assert active.previous_fact_digest == entry.fact_digest
    assert [fact.fact_id for fact in store.load_active_facts()] == [entry.fact_id]


def test_non_admin_cannot_approve_candidate(tmp_path):
    store = CompanyFactStore(root=tmp_path / "facts")
    entry, _audit = _candidate(store)

    with pytest.raises(AdminAuthError):
        store.approve_candidate(entry.fact_id, _admin("manager"))

    assert store.load_fact(entry.fact_id).status == "CANDIDATE"


def test_deprecate_active_removes_from_active_load(tmp_path):
    store = CompanyFactStore(root=tmp_path / "facts")
    entry, _audit = _candidate(store)
    store.approve_candidate(entry.fact_id, _admin())

    deprecated, _deprecate_audit = store.deprecate_fact(entry.fact_id, _admin())

    assert deprecated.status == "DEPRECATED"
    assert store.load_fact(entry.fact_id).status == "DEPRECATED"
    assert store.load_active_facts() == []


def test_index_corruption_raises_load_error(tmp_path):
    store = CompanyFactStore(root=tmp_path / "facts")
    _candidate(store)
    store.index_path.write_text('{"schema_version":"bad","facts":{}}', encoding="utf-8")

    with pytest.raises(CompanyFactLoadError):
        store.list_index_entries()
