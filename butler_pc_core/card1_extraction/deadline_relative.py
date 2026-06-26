from __future__ import annotations

import re
from typing import List

from .parser import extract_deadlines as _base_extract_deadlines

# Extra explicit relative-date patterns used by the card1 pipeline.  They are kept
# outside parser.py to preserve the existing parser contract while improving the
# extract_card1 path for phrases that were being returned as empty deadlines.
_EXTRA_DEADLINE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"(?:이번\s*주\s*|다음\s*주\s*)?(?:월|화|수|목|금|토|일)요일\s*(?:오전|오후)?\s*\d{1,2}시(?:\s*\d{1,2}분)?\s*(?:까지|전까지)"),
    re.compile(r"(?:오늘|내일|모레)\s*(?:오전|오후)?\s*\d{1,2}시(?:\s*\d{1,2}분)?\s*(?:까지|전까지)"),
    re.compile(r"(?:이번\s*주|다음\s*주)\s*(?:월|화|수|목|금|토|일)요일\s*(?:회의|미팅|보고|발표|업무)?\s*(?:전|이전)\s*까지"),
    re.compile(r"(?:회의|미팅|보고|발표|업무)\s*(?:전|이전)\s*까지"),
    re.compile(r"내일\s*(?:전까지|중으로|오전까지|오후까지)"),
    re.compile(r"모레\s*(?:전까지|중으로|오전까지|오후까지)"),
]


def extract_deadlines(text: str) -> List[str]:
    found: List[str] = []
    seen: set[str] = set()
    for pattern in _EXTRA_DEADLINE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(0).strip()
            if raw and raw not in seen:
                seen.add(raw)
                found.append(raw)
    for raw in _base_extract_deadlines(text):
        if raw and raw not in seen:
            seen.add(raw)
            found.append(raw)
    return found
