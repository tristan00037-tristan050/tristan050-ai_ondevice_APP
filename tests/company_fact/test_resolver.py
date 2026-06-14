from __future__ import annotations

import json
from datetime import date

from butler_pc_core.company_fact.resolver import CompanyKnowledgeResolver
from butler_pc_core.company_fact import resolver as resolver_module
from butler_pc_core.company_fact.storage import CompanyFactStore
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.factpack import Fact, FactPack


def _admin() -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text("company-fact-resolver-admin"),
        role="admin",
        admin_session_digest=sha256_text("company-fact-resolver-session"),
        auth_method="test_only",
    )


def _base_pack(answer: str = "Base travel policy answer.") -> FactPack:
    return FactPack(
        facts=[
            Fact(
                id="base_travel_policy_v1",
                category="company_rules",
                question_patterns=["travel reimbursement policy", "travel expense rule"],
                keywords_required=["travel"],
                keywords_any=["reimbursement", "expense", "policy"],
                answer=answer,
                source="base_factpack",
                source_doc="base-policy-v1",
                verified_at=date(2026, 1, 1),
                confidence=1.0,
            )
        ],
        threshold=0.55,
    )


def _save_candidate(store: CompanyFactStore, *, answer: str = "Active company travel policy answer."):
    entry, _audit = store.save_candidate(
        category="company_rules",
        question_patterns=["travel reimbursement policy", "travel expense rule"],
        keywords_required=["travel"],
        keywords_any=["reimbursement", "expense", "policy"],
        answer_runtime_text=answer,
        source="company_admin_verified",
        source_doc="company-handbook-v1",
        verified_at="2026-06-14",
        confidence=0.75,
    )
    return entry


def test_candidate_fact_is_not_served_before_admin_approval(tmp_path):
    store = CompanyFactStore(root=tmp_path / "facts")
    _save_candidate(store, answer="Candidate answer must stay hidden.")

    result = CompanyKnowledgeResolver(base_pack=_base_pack(), company_store=store).resolve(
        "travel reimbursement policy"
    )

    assert result.source == "base"
    assert result.answer == "Base travel policy answer."
    assert result.raw_text_logged is False
    assert result.external_send_zero is True


def test_active_company_fact_overrides_base_fact(tmp_path):
    store = CompanyFactStore(root=tmp_path / "facts")
    candidate = _save_candidate(store, answer="Company approved travel policy answer.")
    store.approve_candidate(candidate.fact_id, _admin())

    result = CompanyKnowledgeResolver(base_pack=_base_pack(), company_store=store).resolve(
        "travel reimbursement policy"
    )

    assert result.source == "company"
    assert result.provenance == "company"
    assert result.fact_id == candidate.fact_id
    assert result.answer == "Company approved travel policy answer."
    assert result.confidence == 1.0
    assert result.fact_digest == store.load_fact(candidate.fact_id).fact_digest


def test_broken_company_fact_is_excluded_while_base_continues(tmp_path):
    store = CompanyFactStore(root=tmp_path / "facts")
    candidate = _save_candidate(store)
    store.approve_candidate(candidate.fact_id, _admin())
    vault_item = tmp_path / "facts" / "vault" / "company_facts" / f"{candidate.fact_id}.json"
    vault_item.unlink()

    result = CompanyKnowledgeResolver(base_pack=_base_pack(), company_store=store).resolve(
        "travel reimbursement policy"
    )

    assert result.source == "base"
    assert result.answer == "Base travel policy answer."
    assert result.fail_class == "COMPANY_FACT_STORE_LOAD_FAILED"


def test_company_store_load_failure_exposes_fail_class_and_serves_base(tmp_path):
    store = CompanyFactStore(root=tmp_path / "facts")
    store.index_path.write_text(json.dumps({"schema_version": "drifted"}), encoding="utf-8")

    result = CompanyKnowledgeResolver(base_pack=_base_pack(), company_store=store).resolve(
        "travel reimbursement policy"
    )

    assert result.source == "base"
    assert result.answer == "Base travel policy answer."
    assert result.fail_class == "COMPANY_FACT_STORE_LOAD_FAILED"


def test_company_fact_conversion_failure_exposes_fail_class_and_serves_base(tmp_path, monkeypatch):
    store = CompanyFactStore(root=tmp_path / "facts")
    candidate = _save_candidate(store)
    store.approve_candidate(candidate.fact_id, _admin())

    def _raise_conversion(_record):
        raise ValueError("conversion failed")

    monkeypatch.setattr(resolver_module, "company_record_to_fact", _raise_conversion)
    result = CompanyKnowledgeResolver(base_pack=_base_pack(), company_store=store).resolve(
        "travel reimbursement policy"
    )

    assert result.source == "base"
    assert result.answer == "Base travel policy answer."
    assert result.fail_class == "COMPANY_FACT_CONVERSION_FAILED"
