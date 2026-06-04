from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StyledDraft:
    draft_text: str
    style_score: float
    forbidden_style_zero: bool


def apply_profile(draft_text: str, profile_ref: str | None = None) -> StyledDraft:
    forbidden = ("무조건", "법적으로 확정", "100%", "보장합니다")
    forbidden_zero = not any(term in draft_text for term in forbidden)
    # Keep text unchanged; style SDK should not overwrite grounding. It annotates style only.
    return StyledDraft(draft_text=draft_text, style_score=0.75 if forbidden_zero else 0.0, forbidden_style_zero=forbidden_zero)
