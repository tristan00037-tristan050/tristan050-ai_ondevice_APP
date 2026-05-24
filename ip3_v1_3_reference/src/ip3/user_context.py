from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from .privacy import sha256_digest

TASK_SCORE = {"coding": 0.9, "analysis": 0.85, "summarization": 0.55, "search": 0.45, "admin": 0.25}
URGENCY_SCORE = {"low": 0.2, "normal": 0.5, "high": 0.75, "critical": 1.0}
ACCURACY_SCORE = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
SENSITIVITY_SCORE = {"Public": 0.1, "Internal": 0.35, "Confidential": 0.75, "Restricted": 1.0}

@dataclass(frozen=True)
class UserContext:
    task_type: str
    urgency: str
    accuracy_requirement: str
    data_sensitivity: str
    request_digest: str
    raw_text_allowed: bool = False

    @classmethod
    def from_metadata(cls, *, task_type: str, urgency: str, accuracy_requirement: str, data_sensitivity: str, request_fingerprint_seed: str) -> "UserContext":
        return cls(
            task_type=task_type,
            urgency=urgency,
            accuracy_requirement=accuracy_requirement,
            data_sensitivity=data_sensitivity,
            request_digest=sha256_digest(request_fingerprint_seed),
            raw_text_allowed=False,
        )

    def scores(self) -> dict[str, float]:
        return {
            "task": TASK_SCORE.get(self.task_type, 0.5),
            "urgency": URGENCY_SCORE.get(self.urgency, 0.5),
            "accuracy": ACCURACY_SCORE.get(self.accuracy_requirement, 0.5),
            "sensitivity": SENSITIVITY_SCORE.get(self.data_sensitivity, 1.0),
        }

    def complexity_score(self) -> float:
        s = self.scores()
        return round((s["task"] * 0.25) + (s["accuracy"] * 0.45) + (s["urgency"] * 0.15) + (s["sensitivity"] * 0.15), 4)
