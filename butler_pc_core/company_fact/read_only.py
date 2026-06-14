from __future__ import annotations

from typing import Any

from butler_pc_core.company_policy.contracts import sha256_text

from .resolver import CompanyKnowledgeResolver


def resolve_read_only_company_knowledge(
    query_runtime_text: str,
    *,
    consumer: str,
    resolver: CompanyKnowledgeResolver | None = None,
) -> dict[str, Any]:
    """Resolve base/company facts for a consumer without mutating any store.

    The caller supplies runtime text, but the returned object carries the query
    digest instead of the query. ACTIVE company facts may be returned as runtime
    answer text for UI/SSE consumption; no candidate or source document body is
    exposed.
    """

    query_text = str(query_runtime_text or "").strip()
    result = (resolver or CompanyKnowledgeResolver()).resolve(query_text) if query_text else None
    answer = result.answer if result is not None else None
    return {
        "schema_version": "company_knowledge.read_only_note.v1",
        "consumer": consumer,
        "query_digest": sha256_text(query_text),
        "answer_runtime_text": answer,
        "answer_digest": sha256_text(answer) if answer else None,
        "source": result.source if result else "none",
        "provenance": result.provenance if result else "none",
        "fact_id": result.fact_id if result else None,
        "fact_digest": result.fact_digest if result else None,
        "confidence": result.confidence if result else 0.0,
        "fail_class": result.fail_class if result else None,
        "mutation_performed": False,
        "raw_text_logged": False,
        "external_send_zero": True,
    }
