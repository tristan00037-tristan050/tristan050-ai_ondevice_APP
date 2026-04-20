from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from .finetune_trigger import FinetuneTrigger
from .knowledge_base import KnowledgeBase
from .team_audit_logger import TeamAuditLogger
from .team_contracts import AccessLevel, CollectResult, DeviceMeta, KBDocument, digest16, scan_for_raw_payload


class DataCollector:
    def __init__(self, knowledge_base: KnowledgeBase, finetune_trigger: FinetuneTrigger, audit_logger: TeamAuditLogger) -> None:
        self.knowledge_base = knowledge_base
        self.finetune_trigger = finetune_trigger
        self.audit_logger = audit_logger
        self.counters: Dict[str, int] = {}

    def receive(self, meta: DeviceMeta | Dict[str, Any]) -> CollectResult:
        payload = asdict(meta) if is_dataclass(meta) else dict(meta)
        found, reason = scan_for_raw_payload(payload)
        team_id = str(payload.get("team_id", "unknown"))
        if found:
            event = self.audit_logger.build_event(
                team_id=team_id,
                user_id=str(payload.get("session_id", "unknown")),
                device_id=str(payload.get("device_id", "unknown")),
                event_type="COLLECT",
                policy_id="policy-ai31-v4",
                data_digest16=digest16(payload),
                access_granted=False,
                reason_code=f"RAW_REJECT:{reason}",
                error_code="RAW",
                selected_route="collect",
                event_code="COLLECT_REJECTED",
            )
            self.audit_logger.append(event)
            return CollectResult(False, team_id, "", self.counters.get(team_id, 0), None, f"RAW_REJECT:{reason}")

        meta_obj = meta if is_dataclass(meta) else DeviceMeta(**payload)
        doc = KBDocument(
            doc_id=digest16({"device": meta_obj.device_id, "session": meta_obj.session_id, "ts": meta_obj.timestamp}),
            title_digest16=digest16({"task": meta_obj.task, "model": meta_obj.selected_model}),
            summary=f"meta:{meta_obj.task}:{meta_obj.selected_model}",
            tags=[meta_obj.task, meta_obj.selected_model],
            version=1,
            lineage_id=digest16({"session": meta_obj.session_id, "task": meta_obj.task}),
            access_level=AccessLevel.TEAM,
            created_at=meta_obj.timestamp,
            team_id=meta_obj.team_id,
            source_ref=f"device:{meta_obj.device_id}",
        )
        idx = self.knowledge_base.index_document(doc)
        new_count = self.finetune_trigger.record_data(meta_obj.team_id, 1)
        self.counters[meta_obj.team_id] = self.counters.get(meta_obj.team_id, 0) + 1
        coverage = self.knowledge_base.get_coverage(meta_obj.team_id)
        job = self.finetune_trigger.check_and_trigger(meta_obj.team_id, coverage_delta=len(coverage.get("topics", {})))
        event = self.audit_logger.build_event(
            team_id=meta_obj.team_id,
            user_id=meta_obj.session_id,
            device_id=meta_obj.device_id,
            event_type="COLLECT",
            policy_id="policy-ai31-v4",
            data_digest16=digest16(meta_obj),
            access_granted=True,
            reason_code="ACCEPTED",
            selected_route="collect",
            event_code="COLLECT_ACCEPTED",
        )
        self.audit_logger.append(event)
        return CollectResult(True, meta_obj.team_id, idx.doc_id, new_count, job.job_id if job else None, "ACCEPTED")

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        stats: Dict[str, Dict[str, int]] = {}
        for team_id, count in self.counters.items():
            stats[team_id] = {
                "collected": count,
                "kb_docs": len(self.knowledge_base.team_documents(team_id)),
                "finetune_counter": self.finetune_trigger.team_counts.get(team_id, 0),
            }
        return stats
