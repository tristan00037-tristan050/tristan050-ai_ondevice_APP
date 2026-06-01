
from __future__ import annotations

from typing import Any

_BLOCK_MARKERS = ("UNSUPPORTED_CLAIM", "CONTRADICTION", "근거없음", "출처없음")

def verify_grounding(draft_text: str | None, evidence_units: list[dict[str, Any]]) -> dict[str, Any]:
    text = draft_text or ""
    source_count = len({unit.get("source_digest") for unit in evidence_units if str(unit.get("source_digest", "")).startswith("sha256:")})
    unsupported = any(marker in text for marker in _BLOCK_MARKERS)
    if not text:
        status = "blocked"
        fail_class = "DRAFT_EMPTY"
    elif not evidence_units:
        status = "needs_review"
        fail_class = "NO_EVIDENCE_UNITS"
    elif unsupported:
        status = "needs_review"
        fail_class = "UNSUPPORTED_CLAIM_DETECTED"
    else:
        status = "pass"
        fail_class = None
    unsupported_claim_rate = 1.0 if unsupported else 0.0
    coverage = min(1.0, source_count / max(1, min(source_count, 3)))
    return {
        "schema_version": "box3.helper4.grounding.contract.v1",
        "status": status,
        "unsupported_claim_rate": unsupported_claim_rate,
        "reference_coverage": coverage if evidence_units else 0.0,
        "grounding_pass_rate": 0.0 if status == "blocked" else (0.94 if status == "needs_review" else 1.0),
        "contradiction_detected": "CONTRADICTION" in text,
        "fail_class": fail_class,
        "external_send_zero": True,
        "plaintext_persisted": False,
    }
