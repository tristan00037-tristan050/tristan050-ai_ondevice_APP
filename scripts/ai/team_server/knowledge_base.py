from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from .team_contracts import AccessLevel, IndexResult, KBDocument, digest16, safe_jsonable, scan_for_raw_payload
from .team_persistence import TeamPersistence


class KnowledgeBase:
    def __init__(self, persistence: TeamPersistence | None = None) -> None:
        self.persistence = persistence
        self.docs_by_team: Dict[str, Dict[str, KBDocument]] = {}
        self.coverage_stats: Dict[str, Dict[str, int]] = {}
        self.zero_hit_topics: Dict[str, int] = {}
        if persistence is not None:
            self._restore(persistence.load_state())

    def _restore(self, state: Dict[str, Any]) -> None:
        kb_snapshot = state.get("kb_snapshot", {}) or {}
        for team_id, docs in kb_snapshot.items():
            self.docs_by_team[team_id] = {}
            for doc_id, raw in docs.items():
                raw = dict(raw)
                raw["access_level"] = AccessLevel(raw["access_level"])
                self.docs_by_team[team_id][doc_id] = KBDocument(**raw)
        self.coverage_stats = state.get("coverage_stats", {}) or {}

    def _persist(self) -> None:
        if self.persistence is None:
            return
        state = self.persistence.load_state()
        kb_snapshot = {
            team_id: {doc_id: safe_jsonable(doc) for doc_id, doc in docs.items()}
            for team_id, docs in self.docs_by_team.items()
        }
        self.persistence.save_state(
            kb_snapshot=kb_snapshot,
            finetune_jobs=state.get("finetune_jobs", {}),
            coverage_stats=self.coverage_stats,
            server_state=state.get("server_state", {}),
        )

    def index_document(self, doc: KBDocument) -> IndexResult:
        found, reason = scan_for_raw_payload(asdict(doc))
        if found:
            return IndexResult(False, doc.doc_id, doc.team_id, f"RAW_REJECT:{reason}")
        team_docs = self.docs_by_team.setdefault(doc.team_id, {})
        team_docs[doc.doc_id] = doc
        team_cov = self.coverage_stats.setdefault(doc.team_id, {})
        for tag in doc.tags:
            team_cov[tag] = team_cov.get(tag, 0) + 1
        self._persist()
        return IndexResult(True, doc.doc_id, doc.team_id, "INDEXED")

    def team_documents(self, team_id: str) -> List[KBDocument]:
        return list(self.docs_by_team.get(team_id, {}).values())

    def get_coverage(self, team_id: str) -> Dict[str, Any]:
        topic_cov = dict(self.coverage_stats.get(team_id, {}))
        return {
            "topics": topic_cov,
            "zero_hit_topics": {k: v for k, v in self.zero_hit_topics.items() if k.startswith(f"{team_id}:")},
            "stale_doc_count": self.stale_doc_count(team_id),
            "coverage_drift": self.coverage_drift(team_id),
        }

    def get_lineage(self, doc_id: str) -> List[Dict[str, Any]]:
        lineage = None
        for docs in self.docs_by_team.values():
            if doc_id in docs:
                lineage = docs[doc_id].lineage_id
                break
        if lineage is None:
            return []
        items: List[Dict[str, Any]] = []
        for docs in self.docs_by_team.values():
            for doc in docs.values():
                if doc.lineage_id == lineage:
                    items.append({
                        "doc_id": doc.doc_id,
                        "version": doc.version,
                        "lineage_id": doc.lineage_id,
                        "title_digest16": doc.title_digest16,
                    })
        return sorted(items, key=lambda x: x["version"])

    def by_access_level(self, team_id: str) -> Dict[str, List[str]]:
        grouped: Dict[str, List[str]] = {}
        for doc in self.team_documents(team_id):
            grouped.setdefault(doc.access_level.value, []).append(doc.doc_id)
        return grouped

    def stale_doc_count(self, team_id: str) -> int:
        now = datetime.now(timezone.utc)
        count = 0
        for doc in self.team_documents(team_id):
            try:
                created = datetime.fromisoformat(doc.created_at.replace("Z", "+00:00"))
                age_days = (now - created).days
            except Exception:
                age_days = 999
            if age_days > 180 or doc.version <= 0:
                count += 1
        return count

    def coverage_drift(self, team_id: str) -> int:
        topics = self.coverage_stats.get(team_id, {})
        if not topics:
            return 0
        vals = list(topics.values())
        return max(vals) - min(vals)

    def record_zero_hit(self, team_id: str, topic: str) -> None:
        key = f"{team_id}:{topic}"
        self.zero_hit_topics[key] = self.zero_hit_topics.get(key, 0) + 1

    def doc_meta(self, doc: KBDocument) -> Dict[str, Any]:
        return {
            "summary": doc.summary,
            "tags": list(doc.tags),
            "lineage_id": doc.lineage_id,
            "access_level": doc.access_level.value,
            "doc_digest16": digest16({"doc_id": doc.doc_id, "title": doc.title_digest16}),
            "source_ref": doc.source_ref,
        }
