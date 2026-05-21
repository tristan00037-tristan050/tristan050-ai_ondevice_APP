"""Card 5 hallucination rollback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class InferenceResult:
    account_title: str
    account_code: str
    needs_review: bool
    match_kind: str
    confidence: float
    rollback_triggered: bool = False
    rollback_reason: Optional[str] = None


def check_and_rollback(result: InferenceResult) -> InferenceResult:
    if result.match_kind == "hallucination":
        result.needs_review = True
        result.rollback_triggered = True
        result.rollback_reason = (
            f"account_title '{result.account_title}' is outside 47 allowlist and alias map"
        )
    return result
