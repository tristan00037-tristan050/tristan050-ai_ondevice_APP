from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from .grounded_prompt import ABSTAINED_SLOT_TEXT
from .v7_fail_class import BLOCK_ABSTAIN_MARKER_INVALID, PARTIAL_BOX3_V7_ABSTAIN_OVERUSE

@dataclass(frozen=True)
class AbstainVerdict:
    valid: bool
    abstain_count: int
    factual_slot_count: int
    abstain_ratio: float
    status: str | None
    fail_class: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

_SLOT_HINTS = ("이름", "날짜", "금액", "결재", "담당자", "법적", "계약", "기한")
_INVALID_ABSTAIN_RE = re.compile(r"근거\s*(없음|부족)|알 수 없음|미확인", re.I)


def evaluate_abstain_usage(draft_text: str) -> AbstainVerdict:
    lines = [line.strip() for line in draft_text.splitlines() if line.strip()]
    factual_slots = [line for line in lines if ":" in line and not line.startswith("제목")]
    if not factual_slots:
        factual_slots = [line for line in lines if any(h in line for h in _SLOT_HINTS)]
    factual_count = max(1, len(factual_slots))
    abstain_count = draft_text.count(ABSTAINED_SLOT_TEXT)
    sanitized_text = draft_text.replace(ABSTAINED_SLOT_TEXT, "")
    invalid = [m.group(0) for m in _INVALID_ABSTAIN_RE.finditer(sanitized_text)]
    if invalid:
        return AbstainVerdict(False, abstain_count, factual_count, abstain_count / factual_count, "BLOCKED", BLOCK_ABSTAIN_MARKER_INVALID)
    ratio = abstain_count / factual_count
    if ratio > 0.60:
        return AbstainVerdict(True, abstain_count, factual_count, round(ratio, 4), PARTIAL_BOX3_V7_ABSTAIN_OVERUSE, PARTIAL_BOX3_V7_ABSTAIN_OVERUSE)
    return AbstainVerdict(True, abstain_count, factual_count, round(ratio, 4), None, None)
