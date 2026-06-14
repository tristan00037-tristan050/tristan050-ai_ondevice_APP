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


def _parse_sse(raw: str) -> dict:
    event = None
    data = None
    for line in raw.splitlines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        if line.startswith("data:"):
            data = json.loads(line.split(":", 1)[1].strip())
    return {"event": event, "data": data}


def test_chat_stream_uses_company_resolver_and_audit_digest_only(monkeypatch):
    import butler_sidecar

    query_text = "company resolver policy"

    class FakeResolver:
        def __init__(self, **_kwargs):
            pass

        def resolve(self, query_runtime_text: str) -> CompanyKnowledgeResolveResult:
            assert query_runtime_text == query_text
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
    params = butler_sidecar._AnalyzeParams(query=query_text)

    async def _collect() -> list[str]:
        return [event async for event in butler_sidecar._stream_analyze(params, "company-knowledge-test")]

    events = asyncio.run(_collect())
    joined = "".join(events)

    assert "company_knowledge" in joined
    assert ANSWER_TEXT in joined
    assert "event: complete" in joined
    assert butler_sidecar._factpack_audit_log
    audit = butler_sidecar._factpack_audit_log[-1].model_dump()
    assert audit["query_digest"] == sha256_text(query_text)
    assert query_text not in json.dumps(audit, ensure_ascii=False)
    assert audit["source"] == "company_fact"


def test_chat_blocks_company_fail_without_answer_before_llm_fallback(monkeypatch):
    import butler_sidecar

    query_text = "company private broken fact"

    class FakeResolver:
        def __init__(self, **_kwargs):
            pass

        def resolve(self, query_runtime_text: str) -> CompanyKnowledgeResolveResult:
            assert query_runtime_text == query_text
            return CompanyKnowledgeResolveResult(
                answer=None,
                source="none",
                provenance="none",
                fact_id=None,
                fact_digest=None,
                fact_source=None,
                source_url=None,
                source_doc=None,
                verified_at=None,
                expires_at=None,
                confidence=0.0,
                fail_class="COMPANY_FACT_STORE_LOAD_FAILED",
            )

    monkeypatch.setattr(butler_sidecar, "CompanyKnowledgeResolver", FakeResolver)
    butler_sidecar._factpack_audit_log.clear()
    params = butler_sidecar._AnalyzeParams(query=query_text)

    async def _collect() -> list[dict]:
        parsed = []
        async for event in butler_sidecar._stream_analyze(params, "company-knowledge-fail-test"):
            parsed.append(_parse_sse(event))
        return parsed

    events = asyncio.run(_collect())
    encoded = json.dumps(events, ensure_ascii=False)

    assert any(event["event"] == "error" for event in events)
    error = [event for event in events if event["event"] == "error"][-1]["data"]
    assert error["error_class"] == "COMPANY_FACT_STORE_LOAD_FAILED"
    assert error["query_digest"] == sha256_text(query_text)
    assert query_text not in json.dumps(error, ensure_ascii=False)
    assert '"source": "llm"' not in encoded
    assert not any(event["event"] == "chunk" for event in events)
    assert butler_sidecar._factpack_audit_log == []


def test_chat_preserves_base_answer_with_degraded_meta(monkeypatch):
    import butler_sidecar

    query_text = "base matched but company degraded"

    class FakeResolver:
        def __init__(self, **_kwargs):
            pass

        def resolve(self, query_runtime_text: str) -> CompanyKnowledgeResolveResult:
            assert query_runtime_text == query_text
            return CompanyKnowledgeResolveResult(
                answer="Base answer remains available.",
                source="base",
                provenance="base",
                fact_id="base-fact-1",
                fact_digest=sha256_text("base-fact-1"),
                fact_source="base_factpack",
                source_url=None,
                source_doc="base-doc",
                verified_at="2026-06-14",
                expires_at=None,
                confidence=1.0,
                fail_class="COMPANY_FACT_STORE_LOAD_FAILED",
            )

    monkeypatch.setattr(butler_sidecar, "CompanyKnowledgeResolver", FakeResolver)
    butler_sidecar._factpack_audit_log.clear()
    params = butler_sidecar._AnalyzeParams(query=query_text)

    async def _collect() -> list[dict]:
        return [
            _parse_sse(event)
            async for event in butler_sidecar._stream_analyze(params, "company-knowledge-degraded-test")
        ]

    events = asyncio.run(_collect())

    assert any(event["event"] == "complete" for event in events)
    assert not any(event["event"] == "error" for event in events)
    assert any(
        event["event"] == "meta"
        and event["data"].get("fail_class") == "COMPANY_FACT_STORE_LOAD_FAILED"
        for event in events
    )
    complete = [event for event in events if event["event"] == "complete"][-1]["data"]
    assert "Base answer remains available." in complete["result_text"]


def test_chat_clean_miss_still_enters_llm_fallback(monkeypatch):
    import butler_sidecar

    query_text = "clean miss should use llm"

    class FakeResolver:
        def __init__(self, **_kwargs):
            pass

        def resolve(self, query_runtime_text: str) -> CompanyKnowledgeResolveResult:
            assert query_runtime_text == query_text
            return CompanyKnowledgeResolveResult(
                answer=None,
                source="none",
                provenance="none",
                fact_id=None,
                fact_digest=None,
                fact_source=None,
                source_url=None,
                source_doc=None,
                verified_at=None,
                expires_at=None,
                confidence=0.0,
                fail_class=None,
            )

    monkeypatch.setattr(butler_sidecar, "CompanyKnowledgeResolver", FakeResolver)
    butler_sidecar._factpack_audit_log.clear()
    params = butler_sidecar._AnalyzeParams(query=query_text)

    async def _collect_until_llm() -> list[dict]:
        parsed = []
        stream = butler_sidecar._stream_analyze(params, "company-knowledge-clean-miss-test")
        try:
            async for event in stream:
                current = _parse_sse(event)
                parsed.append(current)
                if current["event"] == "meta" and current["data"].get("source") == "llm":
                    break
        finally:
            await stream.aclose()
        return parsed

    events = asyncio.run(_collect_until_llm())

    assert any(
        event["event"] == "meta" and event["data"].get("source") == "llm"
        for event in events
    )
    assert not any(event["event"] == "error" for event in events)


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


def test_box2_and_box5_read_only_consumers_degrade_without_substituting_authority():
    class FakeResolver:
        def resolve(self, _query_runtime_text: str) -> CompanyKnowledgeResolveResult:
            return CompanyKnowledgeResolveResult(
                answer=None,
                source="none",
                provenance="none",
                fact_id=None,
                fact_digest=None,
                fact_source=None,
                source_url=None,
                source_doc=None,
                verified_at=None,
                expires_at=None,
                confidence=0.0,
                fail_class="COMPANY_FACT_STORE_LOAD_FAILED",
            )

    for consumer in ("box2_document_transform", "box5_accounting_report"):
        note = resolve_read_only_company_knowledge(
            "degraded company knowledge",
            consumer=consumer,
            resolver=FakeResolver(),  # type: ignore[arg-type]
        )

        assert note["consumer"] == consumer
        assert note["fail_class"] == "COMPANY_FACT_STORE_LOAD_FAILED"
        assert note["source"] == "none"
        assert note["answer_runtime_text"] is None
        assert note["answer_digest"] is None
        assert note["mutation_performed"] is False
        assert note["raw_text_logged"] is False
