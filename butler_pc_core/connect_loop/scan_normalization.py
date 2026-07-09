"""Raw-zero DLP scan normalization for connect-loop ingress points."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

MAX_SCAN_CHARS = 200_000

DLP_DETECTED_RAW = "DLP_DETECTED_RAW"
DLP_DETECTED_NORMALIZED_VARIANT = "DLP_DETECTED_NORMALIZED_VARIANT"
SCAN_INPUT_TOO_LONG = "SCAN_INPUT_TOO_LONG"


@dataclass(frozen=True)
class ScanVariant:
    variant_id: str
    text: str


@dataclass(frozen=True)
class DlpScanResult:
    detected: bool
    reason_code: str | None
    variant_id: str | None = None
    pattern_id: str | None = None
    too_long: bool = False


_ZERO_WIDTH_CHARS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
    "\ufe0e",
    "\ufe0f",
}
_NOISE_CATEGORIES = {"So", "Sk", "Cf", "Cs", "Co", "Mn", "Me"}
_SEPARATOR_RE = re.compile(r"[\s.\-_/:\u058a\u05be\u1400\u1806\u2010-\u2015\u2e17\u2e1a\u2e3a\u2e3b\u30a0\ufe31\ufe32\ufe58\ufe63\uff0d]+")
_KOREAN_DIGIT_TOKENS = (
    ("아홉", "9"),
    ("여덟", "8"),
    ("일곱", "7"),
    ("여섯", "6"),
    ("다섯", "5"),
    ("하나", "1"),
    ("둘", "2"),
    ("셋", "3"),
    ("넷", "4"),
)
_KOREAN_DIGIT_CHARS = str.maketrans(
    {
        "영": "0",
        "공": "0",
        "빵": "0",
        "일": "1",
        "이": "2",
        "삼": "3",
        "사": "4",
        "오": "5",
        "육": "6",
        "륙": "6",
        "칠": "7",
        "팔": "8",
        "구": "9",
    }
)
_CONSERVATIVE_CONFUSABLES = str.maketrans(
    {
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
    }
)


def _unicode_decimal_digits(text: str) -> str:
    out: list[str] = []
    for char in text:
        try:
            out.append(str(unicodedata.decimal(char)))
        except (TypeError, ValueError):
            out.append(char)
    return "".join(out)


def _strip_zero_width(text: str) -> str:
    return "".join(char for char in text if char not in _ZERO_WIDTH_CHARS)


def _strip_visual_noise(text: str) -> str:
    return "".join(char for char in text if unicodedata.category(char) not in _NOISE_CATEGORIES)


def _map_korean_digits(text: str) -> str:
    mapped = text
    for source, target in _KOREAN_DIGIT_TOKENS:
        mapped = mapped.replace(source, target)
    return mapped.translate(_KOREAN_DIGIT_CHARS)


def _strip_separators(text: str) -> str:
    return _SEPARATOR_RE.sub("", text)


def scan_variants(text: str) -> list[ScanVariant]:
    raw = str(text or "")
    v1 = _unicode_decimal_digits(_strip_zero_width(unicodedata.normalize("NFKC", raw).translate(_CONSERVATIVE_CONFUSABLES)))
    v2 = _strip_visual_noise(v1)
    v3 = _map_korean_digits(v2)
    v4 = _strip_separators(v3)
    candidates = (
        ScanVariant("v0_raw", raw),
        ScanVariant("v1_nfkc_zero_width_decimal", v1),
        ScanVariant("v2_visual_noise_removed", v2),
        ScanVariant("v3_korean_digits", v3),
        ScanVariant("v4_separators_removed", v4),
    )
    variants: list[ScanVariant] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.text in seen:
            continue
        seen.add(candidate.text)
        variants.append(candidate)
    return variants


def _iter_patterns(patterns: Mapping[str, Any] | Iterable[Any]) -> Iterable[tuple[str, Any]]:
    if isinstance(patterns, Mapping):
        for key, pattern in patterns.items():
            yield str(key), pattern
        return
    for idx, pattern in enumerate(patterns):
        yield f"pattern_{idx}", pattern


def _pattern_hits(pattern: Any, text: str) -> bool:
    if hasattr(pattern, "search"):
        return bool(pattern.search(text))
    if callable(pattern):
        return bool(pattern(text))
    return False


def detect_any(patterns: Mapping[str, Any] | Iterable[Any], text: str, *, max_scan_chars: int = MAX_SCAN_CHARS) -> DlpScanResult:
    value = str(text or "")
    if len(value) > max_scan_chars:
        return DlpScanResult(True, SCAN_INPUT_TOO_LONG, None, None, True)
    for variant in scan_variants(value):
        for pattern_id, pattern in _iter_patterns(patterns):
            if not _pattern_hits(pattern, variant.text):
                continue
            reason_code = DLP_DETECTED_RAW if variant.variant_id == "v0_raw" else DLP_DETECTED_NORMALIZED_VARIANT
            return DlpScanResult(True, reason_code, variant.variant_id, pattern_id, False)
    return DlpScanResult(False, None, None, None, False)
