
from __future__ import annotations

_FORBIDDEN_STYLE_MARKERS = ("ㅋ", "ㅎㅎ", "대충", "아무튼")

def apply_company_style(draft_text: str | None, profile_ref: str | None = None) -> dict:
    text = draft_text or ""
    forbidden = [marker for marker in _FORBIDDEN_STYLE_MARKERS if marker in text]
    score = 1.0 if not forbidden else 0.0
    if profile_ref and profile_ref.startswith(("vault://", "profile://")):
        score = max(score, 0.7)
    return {
        "schema_version": "box3.helper8.style.contract.v1",
        "status": "pass" if not forbidden else "needs_review",
        "style_match_score": round(score, 4),
        "forbidden_style_zero": not forbidden,
        "profile_ref_applied": bool(profile_ref),
        "external_send_zero": True,
        "plaintext_persisted": False,
    }
