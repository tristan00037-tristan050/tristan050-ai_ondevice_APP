
from __future__ import annotations

_REQUIRED_SECTIONS = ("제목", "목적", "근거", "초안", "확인 필요")

def apply_format(draft_text: str | None, required_sections: tuple[str, ...] = _REQUIRED_SECTIONS) -> dict:
    text = draft_text or ""
    present = [section for section in required_sections if section in text]
    score = len(present) / len(required_sections)
    return {
        "schema_version": "box3.helper3.format.contract.v1",
        "status": "pass" if score >= 0.85 else "needs_review",
        "format_match_score": round(score, 4),
        "required_sections": list(required_sections),
        "missing_sections": [section for section in required_sections if section not in present],
        "external_send_zero": True,
        "plaintext_persisted": False,
    }
