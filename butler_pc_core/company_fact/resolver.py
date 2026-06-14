from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from butler_pc_core.company_policy.contracts import stable_json_digest
from butler_pc_core.factpack import Fact, FactPack, FactMatch

from .storage import CompanyFactLoadError, CompanyFactStore


@dataclass(frozen=True)
class CompanyKnowledgeResolveResult:
    answer: str | None
    source: str
    provenance: str
    fact_id: str | None
    fact_digest: str | None
    fact_source: str | None
    source_url: str | None
    source_doc: str | None
    verified_at: str | None
    expires_at: str | None
    confidence: float
    fail_class: str | None
    raw_text_logged: bool = False
    external_send_zero: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "company_knowledge.resolve_result.v1",
            "answer": self.answer,
            "source": self.source,
            "provenance": self.provenance,
            "fact_id": self.fact_id,
            "fact_digest": self.fact_digest,
            "fact_source": self.fact_source,
            "source_url": self.source_url,
            "source_doc": self.source_doc,
            "verified_at": self.verified_at,
            "expires_at": self.expires_at,
            "confidence": self.confidence,
            "fail_class": self.fail_class,
            "raw_text_logged": self.raw_text_logged,
            "external_send_zero": self.external_send_zero,
        }


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def company_record_to_fact(record) -> Fact:
    return Fact(
        id=record.fact_id,
        category=record.category,
        question_patterns=record.question_patterns,
        keywords_required=record.keywords_required,
        keywords_any=record.keywords_any,
        answer=record.answer_runtime_text,
        source=record.source,
        source_url=record.source_url,
        source_doc=record.source_doc,
        verified_at=_parse_date(record.verified_at) or date.today(),
        expires_at=_parse_date(record.expires_at),
        confidence=1.0,
    )


def _base_fact_digest(match: FactMatch) -> str:
    return stable_json_digest(match.fact.model_dump(mode="json"))


class CompanyKnowledgeResolver:
    def __init__(
        self,
        *,
        base_pack: FactPack | None = None,
        company_store: CompanyFactStore | None = None,
    ) -> None:
        self.base_pack = base_pack or FactPack.from_default_facts_dir()
        self.company_store = company_store or CompanyFactStore()

    def _company_pack(self) -> tuple[FactPack | None, dict[str, str], str | None]:
        try:
            records = self.company_store.load_active_facts()
        except CompanyFactLoadError:
            return None, {}, "COMPANY_FACT_STORE_LOAD_FAILED"
        try:
            facts = [company_record_to_fact(record) for record in records if record.status == "ACTIVE"]
        except Exception:
            return None, {}, "COMPANY_FACT_CONVERSION_FAILED"
        if not facts:
            return None, {}, None
        try:
            pack = FactPack(facts=facts, threshold=self.base_pack.matcher.threshold)
        except Exception:
            return None, {}, "COMPANY_FACT_CONVERSION_FAILED"
        digest_by_fact_id = {record.fact_id: record.fact_digest for record in records if record.status == "ACTIVE"}
        return pack, digest_by_fact_id, None

    def resolve(self, query_runtime_text: str) -> CompanyKnowledgeResolveResult:
        base_match = self.base_pack.lookup(query_runtime_text)
        company_pack, company_digests, fail_class = self._company_pack()
        company_match = company_pack.lookup(query_runtime_text) if company_pack is not None else None

        if company_match is not None:
            return CompanyKnowledgeResolveResult(
                answer=company_match.fact.answer,
                source="company",
                provenance="company",
                fact_id=company_match.fact.id,
                fact_digest=company_digests.get(company_match.fact.id) or _base_fact_digest(company_match),
                fact_source=company_match.fact.source,
                source_url=company_match.fact.source_url,
                source_doc=company_match.fact.source_doc,
                verified_at=company_match.fact.verified_at.isoformat(),
                expires_at=company_match.fact.expires_at.isoformat() if company_match.fact.expires_at else None,
                confidence=company_match.fact.confidence,
                fail_class=fail_class,
            )
        if base_match is not None:
            return CompanyKnowledgeResolveResult(
                answer=base_match.fact.answer,
                source="base",
                provenance="base",
                fact_id=base_match.fact.id,
                fact_digest=_base_fact_digest(base_match),
                fact_source=base_match.fact.source,
                source_url=base_match.fact.source_url,
                source_doc=base_match.fact.source_doc,
                verified_at=base_match.fact.verified_at.isoformat(),
                expires_at=base_match.fact.expires_at.isoformat() if base_match.fact.expires_at else None,
                confidence=base_match.fact.confidence,
                fail_class=fail_class,
            )
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
            fail_class=fail_class,
        )
