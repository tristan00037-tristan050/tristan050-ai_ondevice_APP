from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .knowledge_base import KnowledgeBase
from .policy_enforcer import PolicyEnforcer
from .team_contracts import ACCESS_ORDER, AccessLevel, RAGRequest, RAGResponse


class RAGEngine:
    def __init__(self, knowledge_base: KnowledgeBase, policy_enforcer: PolicyEnforcer) -> None:
        self.knowledge_base = knowledge_base
        self.policy_enforcer = policy_enforcer
        self.query_count = 0
        self.hit_queries = 0
        self.zero_hit_queries = 0
        self.total_relevance = 0.0
        self.total_results = 0
        self.top1_total = 0.0
        self.top1_count = 0
        self.access_filtered_count = 0
        self.rejected_by_policy_count = 0
        self.stale_penalty_applied = False
        self.query_coverage_bucket = "low"

    def _score(self, req: RAGRequest, doc_summary: str, tags: list[str], version: int, stale: bool) -> float:
        summary_overlap = 1.0 if req.query_digest16[:4] in doc_summary else 0.35
        tag_overlap = 1.0 if any(tag[:3] in req.query_digest16 for tag in tags if tag) else 0.45
        freshness = 1.0 if version >= 1 else 0.2
        score = (summary_overlap + tag_overlap + freshness) / 3.0
        if stale:
            score -= 0.15
            self.stale_penalty_applied = True
        return round(max(score, 0.0), 4)

    def _bucket(self, result_count: int, requested: int) -> str:
        ratio = 0.0 if requested <= 0 else result_count / requested
        if ratio >= 0.8:
            return "high"
        if ratio >= 0.4:
            return "medium"
        return "low"

    def query(self, req: RAGRequest, context: Dict[str, Any]) -> RAGResponse:
        self.query_count += 1
        pre_candidates: List[Tuple[float, Dict[str, Any], AccessLevel]] = []
        denied = 0
        for doc in self.knowledge_base.team_documents(req.team_id):
            stale = self.knowledge_base.stale_doc_count(req.team_id) > 0 and doc.version <= 0
            pre_candidates.append((self._score(req, doc.summary, doc.tags, doc.version, stale), self.knowledge_base.doc_meta(doc), doc.access_level))

        ranked = sorted(pre_candidates, key=lambda item: (item[0], -ACCESS_ORDER[item[2]]), reverse=True)
        filtered: List[Tuple[float, Dict[str, Any], AccessLevel]] = []
        for score, meta, level in ranked:
            decision = self.policy_enforcer.check(req.user_id, req.team_id, "rag_query", {"access_level": level.value}, context)
            if not decision.allowed:
                denied += 1
                self.access_filtered_count += 1
                self.rejected_by_policy_count += 1
                continue
            filtered.append((score, meta, level))

        results: List[Dict[str, Any]] = []
        for score, meta, _ in filtered[: req.top_k]:
            results.append({**meta, "relevance": score})
            self.total_relevance += score
            self.total_results += 1
        if results:
            self.hit_queries += 1
            self.top1_total += results[0]["relevance"]
            self.top1_count += 1
        else:
            self.zero_hit_queries += 1
            self.knowledge_base.record_zero_hit(req.team_id, req.query_digest16[:4])
        self.query_coverage_bucket = self._bucket(len(results), req.top_k)
        return RAGResponse(hit_count=len(results), results_meta=results, access_denied_count=denied, query_digest16=req.query_digest16)

    @property
    def metrics(self) -> Dict[str, float | int | bool | str]:
        hit_rate = self.hit_queries / self.query_count if self.query_count else 0.0
        zero_hit_rate = self.zero_hit_queries / self.query_count if self.query_count else 0.0
        avg_relevance = self.total_relevance / self.total_results if self.total_results else 0.0
        top1_relevance = self.top1_total / self.top1_count if self.top1_count else 0.0
        stale_doc_count = sum(self.knowledge_base.stale_doc_count(team_id) for team_id in self.knowledge_base.docs_by_team)
        return {
            "hit_rate": round(hit_rate, 4),
            "avg_relevance": round(avg_relevance, 4),
            "zero_hit_rate": round(zero_hit_rate, 4),
            "access_filtered_count": self.access_filtered_count,
            "stale_doc_count": stale_doc_count,
            "top1_relevance": round(top1_relevance, 4),
            "rejected_by_policy_count": self.rejected_by_policy_count,
            "query_coverage_bucket": self.query_coverage_bucket,
            "stale_penalty_applied": self.stale_penalty_applied,
        }
