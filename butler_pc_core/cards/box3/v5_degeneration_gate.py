from __future__ import annotations

from dataclasses import asdict, dataclass
from collections import Counter
import re
from typing import Any

@dataclass(frozen=True)
class DegenerationVerdict:
    degeneration_detected: bool
    fail_class: str | None
    repeated_ngram_ratio: float
    repeated_line_ratio: float
    leaked_prompt_marker: bool
    too_short: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

_PROMPT_MARKERS = ("SYSTEM:", "DECODE:", "FEW_SHOT", "REFERENCES:", "[REF ", "IGNORE PREVIOUS")
_TOKEN_RE = re.compile(r"[A-Za-z가-힣0-9]+")

def _ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    if len(tokens) < n:
        return []
    return [tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)]

def detect_v5_degeneration(draft_text: str, *, ngram_n: int = 4) -> DegenerationVerdict:
    text = draft_text or ""
    tokens = _TOKEN_RE.findall(text.casefold())
    grams = _ngrams(tokens, ngram_n)
    if grams:
        counts = Counter(grams)
        repeated = sum(count - 1 for count in counts.values() if count > 1)
        repeated_ngram_ratio = repeated / max(1, len(grams))
    else:
        repeated_ngram_ratio = 0.0

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        counts = Counter(lines)
        repeated_line_ratio = sum(count - 1 for count in counts.values() if count > 1) / len(lines)
    else:
        repeated_line_ratio = 0.0

    leaked_prompt_marker = any(marker.casefold() in text.casefold() for marker in _PROMPT_MARKERS)
    too_short = len(tokens) < 8
    detected = repeated_ngram_ratio > 0.18 or repeated_line_ratio > 0.25 or leaked_prompt_marker or too_short
    fail = "BLOCK_DEGENERATION" if detected else None
    return DegenerationVerdict(detected, fail, round(repeated_ngram_ratio, 4), round(repeated_line_ratio, 4), leaked_prompt_marker, too_short)
