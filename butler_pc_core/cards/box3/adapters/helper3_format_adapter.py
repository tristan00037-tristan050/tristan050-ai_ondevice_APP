from __future__ import annotations

from ..draft_service import DEFAULT_REQUIRED_SECTIONS
from ..types import Box3Format


def apply_format_contract(draft_text: str | None, required_sections: list[str] | None = None) -> Box3Format:
    sections = required_sections or DEFAULT_REQUIRED_SECTIONS
    if not draft_text:
        return {
            "format_match_score": 0.0,
            "required_sections_present": False,
            "required_sections": sections,
        }
    hits = sum(1 for section in sections if section in draft_text)
    score = hits / max(len(sections), 1)
    return {
        "format_match_score": round(score, 4),
        "required_sections_present": hits == len(sections),
        "required_sections": sections,
    }

