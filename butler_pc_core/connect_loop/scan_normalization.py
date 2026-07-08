from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MAX_SCAN_CHARS = 200_000
SCAN_INPUT_TOO_LONG = "SCAN_INPUT_TOO_LONG"
DLP_DETECTED_RAW = "DLP_DETECTED_RAW"
DLP_DETECTED_NORMALIZED_VARIANT = "DLP_DETECTED_NORMALIZED_VARIANT"

_ZERO_WIDTH_CHARS = "\u200b\u200c\u200d\ufeff\u2060"
_HYPHEN_CHARS = "-‐‑‒–—―﹣－"
_SEPARATOR_CHARS = set(" \t\r\n.\-_/:") | set(_HYPHEN_CHARS) | {"：", "ㆍ", "·"}
_VISUAL_NOISE_CATEGORIES = {"So", "Sk", "Cf", "Cs", "Co", "Mn", "Me"}
_KO_DIGITS = {
    "영": "0",
    "공": "0",
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
_CONFUSABLE_DIGITS = str.maketrans({
    "Ｏ": "0", "ｏ": "0", "O": "0", "o": "0",
    "Ｉ": "1", "ｌ": "1", "Ⅰ": "1", "ⅼ": "1",
})


@dataclass(frozen=True)
class ScanVariant:
    variant_id: str
    text: str


@dataclass(frozen=True)
class DlpScanResult:
    detected: bool
    reason_code: str | None = None
    variant_id: str | None = None
    pattern_id: str | None = None
    too_long: bool = False


def _remove_zero_width(text: str) -> str:
    return "".join(ch for ch in text if ch not in _ZERO_WIDTH_CHARS)


def _decimal_to_ascii(text: str) -> str:
    out: list[str] = []
    for ch in text:
        try:
            out.append(str(unicodedata.decimal(ch)))
        except (TypeError, ValueError):
            out.append(ch)
    return "".join(out)


def _nfkc_security_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = _remove_zero_width(normalized)
    normalized = _decimal_to_ascii(normalized)
    return normalized.translate(_CONFUSABLE_DIGITS)


def _remove_visual_noise(text: str) -> str:
    return "".join(ch for ch in text if unicodedata.category(ch) not in _VISUAL_NOISE_CATEGORIES)


def _map_korean_digits(text: str) -> str:
    return "".join(_KO_DIGITS.get(ch, ch) for ch in text)


def _remove_separators(text: str) -> str:
    return "".join(ch for ch in text if ch not in _SEPARATOR_CHARS)


def scan_variants(text: str) -> list[ScanVariant]:
    raw = str(text or "")
    candidates = [
        ScanVariant("v0_raw", raw),
        ScanVariant("v1_nfkc_zero_width_decimal", _nfkc_security_fold(raw)),
    ]
    candidates.append(ScanVariant("v2_visual_noise_removed", _remove_visual_noise(candidates[-1].text)))
    candidates.append(ScanVariant("v3_korean_digits", _map_korean_digits(candidates[-1].text)))
    candidates.append(ScanVariant("v4_separator_removed", _remove_separators(candidates[-1].text)))

    seen: set[str] = set()
    variants: list[ScanVariant] = []
    for item in candidates:
        if item.text in seen:
            continue
        seen.add(item.text)
        variants.append(item)
    return variants


def _iter_patterns(patterns: Mapping[str, Any] | Sequence[Any]) -> list[tuple[str, Any]]:
    if isinstance(patterns, Mapping):
        return [(str(key), value) for key, value in patterns.items()]
    return [(f"pattern_{index}", value) for index, value in enumerate(patterns)]


def _pattern_matches(pattern: Any, text: str) -> bool:
    if hasattr(pattern, "search") and callable(pattern.search):
        return pattern.search(text) is not None
    if isinstance(pattern, str):
        return re.search(pattern, text) is not None
    if callable(pattern):
        return bool(pattern(text))
    raise TypeError("UNSUPPORTED_DLP_PATTERN")


def detect_any(
    patterns: Mapping[str, Any] | Sequence[Any],
    text: str,
    *,
    max_scan_chars: int = MAX_SCAN_CHARS,
) -> DlpScanResult:
    raw = str(text or "")
    if len(raw) > max_scan_chars:
        return DlpScanResult(True, SCAN_INPUT_TOO_LONG, too_long=True)

    normalized_patterns = _iter_patterns(patterns)
    for variant in scan_variants(raw):
        for pattern_id, pattern in normalized_patterns:
            if _pattern_matches(pattern, variant.text):
                return DlpScanResult(
                    True,
                    DLP_DETECTED_RAW if variant.variant_id == "v0_raw" else DLP_DETECTED_NORMALIZED_VARIANT,
                    variant.variant_id,
                    pattern_id,
                    False,
                )
    return DlpScanResult(False)
