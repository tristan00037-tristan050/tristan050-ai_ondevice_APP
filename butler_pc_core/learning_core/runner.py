from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gate import UnifiedLearningIntakeGate
from .queue import ArtifactQueue, QueueAppendResult


@dataclass
class LearningIntakeRunner:
    gate: UnifiedLearningIntakeGate
    queue: ArtifactQueue

    @classmethod
    def default(
        cls, queue_path: str | Path, *, enable_chat: bool = False, chat_run_mode: str = "production"
    ) -> "LearningIntakeRunner":
        return cls(
            UnifiedLearningIntakeGate.with_default_adapters(enable_chat=enable_chat, chat_run_mode=chat_run_mode),
            ArtifactQueue(queue_path),
        )

    def ingest(self, candidate: dict[str, Any]) -> dict[str, Any]:
        verdict = self.gate.evaluate(candidate)
        if not verdict.accepted:
            return {"accepted": False, "drop_reason": verdict.drop_reason, "queue_appended": False}
        append_result: QueueAppendResult = self.queue.append_candidate(verdict.candidate or candidate)
        return {
            "accepted": True,
            "drop_reason": None,
            "queue_appended": append_result.appended,
            "queue_reason": append_result.reason,
            "record_digest": append_result.record_digest,
        }
