from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .contracts import assert_no_forbidden_fields, stable_json, stable_json_digest


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class QueueAppendResult:
    appended: bool
    reason: str
    record_digest: str | None = None


class ArtifactQueue:
    """Append-only digest/ref queue with idempotent candidate handling.

    The queue stores candidates only after UnifiedLearningIntakeGate accepts them.
    It never stores raw files, prompts, responses, local paths, or plain account data.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            assert_no_forbidden_fields(item)
            records.append(item)
        return records

    def append_candidate(self, candidate: dict[str, Any], *, status: str = "active") -> QueueAppendResult:
        assert_no_forbidden_fields(candidate)
        if status not in {"active", "replaced", "removed"}:
            return QueueAppendResult(False, "QUEUE_STATUS_INVALID")
        candidate_digest = stable_json_digest(candidate)
        existing = self.read_records()
        for record in existing:
            if record.get("candidate_id") == candidate.get("candidate_id") and record.get("candidate_digest") == candidate_digest:
                return QueueAppendResult(False, "IDEMPOTENT_DUPLICATE", record.get("record_digest"))

        previous_digest = next(
            (
                record.get("candidate_digest")
                for record in reversed(existing)
                if record.get("candidate_id") == candidate.get("candidate_id")
            ),
            None,
        )
        record = {
            "schema_version": "learning_artifact_queue_record.v1",
            "candidate_id": candidate["candidate_id"],
            "target_kind": candidate["target_kind"],
            "candidate_digest": candidate_digest,
            "payload_digest": candidate["payload_digest"],
            "expected_effect_digest": candidate["expected_effect_digest"],
            "queue_status": status if previous_digest is None else "replaced",
            "previous_candidate_digest": previous_digest,
            "human_review_required": True,
            "auto_apply_to_runtime": False,
            "retention_class": "audit_digest_only",
            "created_at": _now(),
        }
        record["record_digest"] = stable_json_digest({k: v for k, v in record.items() if k != "record_digest"})
        assert_no_forbidden_fields(record)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(stable_json(record) + "\n")
        return QueueAppendResult(True, "APPENDED", record["record_digest"])
