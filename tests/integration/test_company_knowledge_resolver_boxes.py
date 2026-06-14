from __future__ import annotations

import asyncio
import json

import pandas as pd

from butler_pc_core.accounting.report import build_summary
from butler_pc_core.company_fact.read_only import resolve_read_only_company_knowledge
from butler_pc_core.company_fact.resolver import (
    CompanyKnowledgeResolver,
    CompanyKnowledgeResolveResult,
)
from butler_pc_core.company_fact.storage import CompanyFactStore
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text


ANSWER_TEXT = "Company approved policy answer for resolver consumers."


def _admin() -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text("company-knowledge-box-admin"),
        role="admin",
        admin_session_digest=sha256_text("company-knowledge-box-session"),
        auth_method="test_only",
    )


def _active_store(tmp_path) -> CompanyFactStore:
    store = CompanyFactStore(root=tmp_path / "facts")
    entry, _audit = store.save_candidate(
        category="company_rules",
        question_patterns=["company resolver policy", "resolver company rule"],
        keywords_required=["resolver"],
        keywords_any=["policy", "company"],
        answer_runtime_text=ANSWER_TEXT,
        source="company_admin_verified",
        source_doc="resolver-policy-v1",
        verified_at="2026-06-14",
        confidence=0.8,
    )
    store.approve_candidate(entry.fact_id, _admin())
    return store


def test_chat_stream_uses_company_resolver_and_audit_digest_only(monkeypatch):
    import butler_sidecar

    raw_query = "company resolver policy"

    class FakeResolver:
        def __init__(self, **_kwargs):
            pass

        def resolve(self, query_runtime_text: str) -> CompanyKnowledgeResolveResult:
            assert query_runtime_text == raw_query
            return CompanyKnowledgeResolveResult(
                answer=ANSWER_TEXT,
                source="company",
                provenance="company",
                fact_id="company-fact-chat",
                fact_digest=sha256_text("company-fact-chat"),
                fact_source="company_admin_verified",
                source_url=None,
                source_doc="resolver-policy-v1",
                verified_at="2026-06-14",
                expires_at=None,
                confidence=1.0,
                fail_class=None,
            )

    monkeypatch.setattr(butler_sidecar, "CompanyKnowledgeResolver", FakeResolver)
    butler_sidecar._factpack_audit_log.clear()
    params = butler_sidecar._AnalyzeParams(query=raw_query)

    async def _collect() -> list[str]:
        return [event async for event in butler_sidecar._stream_analyze(params, "company-knowledge-test")]

    events = asyncio.run(_collect())
    joined = "".join(events)

    assert "company_knowledge" in joined
    assert ANSWER_TEXT in joined
    assert "event: complete" in joined
    assert butler_sidecar._factpack_audit_log
    audit = butler_sidecar._factpack_audit_log[-1].model_dump()
    assert audit["query_digest"] == sha256_text(raw_query)
    assert raw_query not in json.dumps(audit, ensure_ascii=False)
    assert audit["source"] == "company_fact"


def test_box2_read_only_company_knowledge_note_serves_active_only(tmp_path):
    store = _active_store(tmp_path)
    resolver = CompanyKnowledgeResolver(company_store=store)

    note = resolve_read_only_company_knowledge(
        "company resolver policy",
        consumer="box2_document_transform",
        resolver=resolver,
    )

    assert note["consumer"] == "box2_document_transform"
    assert note["source"] == "company"
    assert note["answer_runtime_text"] == ANSWER_TEXT
    assert note["mutation_performed"] is False
    assert note["raw_text_logged"] is False
    assert note["external_send_zero"] is True
    assert note["query_digest"] == sha256_text("company resolver policy")
    assert len(store.list_index_entries(status="ACTIVE")) == 1


def test_box5_read_only_note_does_not_change_accounting_categories(tmp_path):
    store = _active_store(tmp_path)
    resolver = CompanyKnowledgeResolver(company_store=store)
    df = pd.DataFrame(
        [
            {"분류과목": "용역매출", "신뢰도": 0.9, "_amt": 100000},
            {"분류과목": "지급수수료", "신뢰도": 0.8, "_amt": -3000},
        ]
    )
    summary_before = build_summary(df)

    note = resolve_read_only_company_knowledge(
        "company resolver policy",
        consumer="box5_accounting_report",
        resolver=resolver,
    )
    summary_after = dict(summary_before)
    summary_after["company_knowledge"] = note

    assert note["consumer"] == "box5_accounting_report"
    assert note["source"] == "company"
    assert summary_after["categories"] == summary_before["categories"]
    assert summary_after["total_rows"] == summary_before["total_rows"]
    assert summary_after["classified_rows"] == summary_before["classified_rows"]
