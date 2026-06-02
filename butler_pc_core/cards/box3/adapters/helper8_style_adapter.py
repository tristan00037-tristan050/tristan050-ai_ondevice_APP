from __future__ import annotations

from ..types import Box3Style


FORBIDDEN_STYLE_MARKERS = ("해요", "ㅋㅋ", "!!", "확정합니다")


def apply_style_contract(draft_text: str | None) -> Box3Style:
    if not draft_text:
        return {"style_match_score": 0.0, "forbidden_style_zero": True}
    forbidden_count = sum(1 for marker in FORBIDDEN_STYLE_MARKERS if marker in draft_text)
    formal_markers = sum(1 for marker in ("합니다", "습니다", "확인 필요") if marker in draft_text)
    score = min(1.0, 0.70 + 0.10 * formal_markers)
    if forbidden_count:
        score = min(score, 0.40)
    return {
        "style_match_score": round(score, 4),
        "forbidden_style_zero": forbidden_count == 0,
    }

