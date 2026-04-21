from __future__ import annotations
from collections import defaultdict, Counter
from typing import List, Dict
from .central_contracts import EnterpriseKBDoc, IndexResult

class EnterpriseKB:
    def __init__(self):
        self.docs: Dict[str, EnterpriseKBDoc] = {}
        self.lineage: Dict[str, List[str]] = defaultdict(list)

    def index_document(self, doc: EnterpriseKBDoc) -> IndexResult:
        self.docs[doc.doc_id] = doc
        self.lineage[doc.lineage_id].append(doc.doc_id)
        return IndexResult(ok=True, doc_id=doc.doc_id, indexed_count=len(self.docs))

    def get_coverage(self):
        topic = Counter()
        teams = set()
        stale = 0
        for doc in self.docs.values():
            for tag in doc.tags:
                topic[tag] += 1
            teams.add(doc.team_id)
            if doc.version < max([d.version for d in self.docs.values() if d.lineage_id == doc.lineage_id]):
                stale += 1
        return {"topic_coverage": dict(topic), "team_diversity": len(teams), "stale_doc_count": stale}

    def get_lineage(self, doc_id: str):
        doc = self.docs[doc_id]
        return [self.docs[x] for x in self.lineage[doc.lineage_id]]

    def query(self, query_summary: str, tags: list[str], top_k: int = 3, allowed_teams: list[str] | None = None):
        allowed_teams = allowed_teams or []
        scored = []
        rejected_by_policy = 0
        qwords = set(query_summary.lower().split())
        for doc in self.docs.values():
            summary_words = set(doc.summary.lower().split())
            summary_overlap = len(qwords & summary_words) / max(1, len(qwords | summary_words))
            tag_overlap = len(set(tags) & set(doc.tags)) / max(1, len(set(tags) | set(doc.tags)))
            freshness = min(1.0, doc.version / max(1, max(d.version for d in self.docs.values() if d.lineage_id == doc.lineage_id)))
            stale_penalty = 0.1 if freshness < 1.0 else 0.0
            score = round((summary_overlap * 0.45) + (tag_overlap * 0.35) + (freshness * 0.2) - stale_penalty, 4)
            if allowed_teams and doc.team_id not in allowed_teams:
                rejected_by_policy += 1
                continue
            scored.append((score, stale_penalty > 0, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]
        result_docs = [{
            "doc_id": d.doc_id,
            "summary": d.summary,
            "tags": d.tags,
            "team_id": d.team_id,
            "version": d.version,
            "lineage_id": d.lineage_id,
            "relevance": s,
            "title_digest16": d.title_digest16,
        } for s, _, d in top]
        top1 = top[0][0] if top else 0.0
        zero_hit_reason = "NO_DOCS" if not self.docs else ("POLICY_FILTERED" if rejected_by_policy and not result_docs else ("LOW_MATCH" if not result_docs else ""))
        cov = "high" if top1 >= 0.66 else ("medium" if top1 >= 0.33 else "low")
        teams = [d["team_id"] for d in result_docs]
        diversity = len(set(teams)) / max(1, len(teams))
        return {
            "results": result_docs,
            "top1_relevance": top1,
            "zero_hit_reason": zero_hit_reason,
            "query_coverage_bucket": cov,
            "top_k_after_policy_filter": len(result_docs),
            "result_diversity_score": diversity,
            "stale_penalty_applied": any(sp for _, sp, _ in top),
            "rejected_by_policy_count": rejected_by_policy,
        }
