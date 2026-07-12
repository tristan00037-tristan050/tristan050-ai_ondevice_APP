"""Raw-zero Unicode normalization primitives for Butler DLP scanning.

This module owns normalization only. It never logs or returns normalized text;
callers receive variant/pattern identifiers without matched substrings.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

MAX_SCAN_CHARS = 200_000

DLP_DETECTED_RAW = "DLP_DETECTED_RAW"
DLP_DETECTED_NORMALIZED_VARIANT = "DLP_DETECTED_NORMALIZED_VARIANT"
SCAN_INPUT_TOO_LONG = "SCAN_INPUT_TOO_LONG"

_OBSERVED_CONFUSABLE_SCHEMA = "butler.observed_confusable_codepoints.v1"
_OBSERVED_CONFUSABLE_PATH = Path(__file__).with_name("observed_confusable_codepoints.v1.json")
_CONFUSABLE_CONTEXT_RE = re.compile(r"(?i)(계좌|입금|상환|예금|카드|전화|연락|휴대폰|주민|주민등록|account|acct|card|phone|tel|mobile|rrn|resident)")


@dataclass(frozen=True)
class ScanVariant:
    variant_id: str
    text: str

    def __repr__(self) -> str:
        return f"ScanVariant(variant_id={self.variant_id!r}, text=<redacted:{len(self.text)}>)"


@dataclass(frozen=True)
class DlpScanResult:
    detected: bool
    reason_code: str | None
    variant_id: str | None = None
    pattern_id: str | None = None
    too_long: bool = False


_ZERO_WIDTH_CHARS = {
    "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff", "\ufe0e", "\ufe0f",
}
_NOISE_CATEGORIES = {"So", "Sk", "Cf", "Cs", "Co", "Mn", "Me"}
_INTRA_TOKEN_SEPARATOR_RE = re.compile(r"[.\-_/\:\u058a\u05be\u1400\u1806\u2010-\u2015\u2e17\u2e1a\u2e3a\u2e3b\u30a0\ufe31\ufe32\ufe58\ufe63\uff0d]+")
_WHITESPACE_RE = re.compile(r"\s+")
_KOREAN_DIGIT_TOKENS = (
    ("아홉", "9"), ("여덟", "8"), ("일곱", "7"), ("여섯", "6"),
    ("다섯", "5"), ("하나", "1"), ("둘", "2"), ("셋", "3"), ("넷", "4"),
)
_KOREAN_DIGIT_CHARS = str.maketrans(
    {"영":"0","공":"0","빵":"0","일":"1","이":"2","삼":"3","사":"4","오":"5","육":"6","륙":"6","칠":"7","팔":"8","구":"9"}
)


def _load_observed_confusables(path: Path = _OBSERVED_CONFUSABLE_PATH) -> dict[str, str]:
    """Load explicit U+XXXX→ASCII digit mappings; unknown/invalid data fails closed.

    An absent file means no additional confusable mapping. ASCII O/I/l are never
    accepted, even if a malformed corpus export tries to add them.
    """
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != _OBSERVED_CONFUSABLE_SCHEMA:
        raise ValueError("CONFUSABLE_ALLOWLIST_SCHEMA_INVALID")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("CONFUSABLE_ALLOWLIST_ENTRIES_INVALID")
    mapping: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"codepoint", "ascii_digit", "category", "count"}:
            raise ValueError("CONFUSABLE_ALLOWLIST_ENTRY_INVALID")
        codepoint = item["codepoint"]
        digit = item["ascii_digit"]
        count = item["count"]
        if not isinstance(codepoint, str) or not re.fullmatch(r"U\+[0-9A-F]{4,6}", codepoint):
            raise ValueError("CONFUSABLE_CODEPOINT_INVALID")
        if not isinstance(digit, str) or not re.fullmatch(r"[0-9]", digit):
            raise ValueError("CONFUSABLE_DIGIT_INVALID")
        if not isinstance(item["category"], str) or not item["category"]:
            raise ValueError("CONFUSABLE_CATEGORY_INVALID")
        if not isinstance(count, int) or count < 1:
            raise ValueError("CONFUSABLE_COUNT_INVALID")
        char = chr(int(codepoint[2:], 16))
        if char in {"O", "I", "l", "o"}:
            raise ValueError("ASCII_CONFUSABLE_GLOBAL_MAPPING_FORBIDDEN")
        normalized = unicodedata.normalize("NFKC", char)
        try:
            normalized = str(unicodedata.decimal(normalized))
        except (TypeError, ValueError):
            pass
        if normalized == digit:
            continue
        mapping[char] = digit
    return mapping


_OBSERVED_CONFUSABLES = _load_observed_confusables()


def _decimal_count(text: str) -> int:
    count = 0
    for char in text:
        try:
            unicodedata.decimal(char)
            count += 1
        except (TypeError, ValueError):
            continue
    return count


def _apply_contextual_observed_confusables(text: str, mapping: Mapping[str, str] | None = None) -> str:
    """Apply corpus-observed mappings only inside narrow numeric contexts.

    Condition A: at least six real decimal digits in a <=24-character window.
    Condition B: a sensitive-number context word and at least four real digits.
    """
    active = dict(_OBSERVED_CONFUSABLES if mapping is None else mapping)
    if not active or not any(char in active for char in text):
        return text
    chars = list(text)
    for index, char in enumerate(chars):
        replacement = active.get(char)
        if replacement is None:
            continue
        start = max(0, index - 12)
        end = min(len(chars), index + 12)
        window = "".join(chars[start:end])
        wide_start = max(0, index - 32)
        wide_end = min(len(chars), index + 32)
        wide = "".join(chars[wide_start:wide_end])
        if _decimal_count(window) >= 6 or (_decimal_count(wide) >= 4 and _CONFUSABLE_CONTEXT_RE.search(wide)):
            chars[index] = replacement
    return "".join(chars)


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
    tokens = _WHITESPACE_RE.split(text)
    return " ".join(_INTRA_TOKEN_SEPARATOR_RE.sub("", token) for token in tokens)


def _strip_separators_conditional_merge(text: str) -> str:
    tokens = _WHITESPACE_RE.split(text)
    groups: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        stripped = _INTRA_TOKEN_SEPARATOR_RE.sub("", token)
        is_structured = stripped != token
        if is_structured:
            if current:
                groups.append(current)
                current = []
            groups.append([stripped])
        else:
            current.append(stripped)
    if current:
        groups.append(current)
    return " ".join("".join(group) for group in groups)


def scan_variants(text: str) -> list[ScanVariant]:
    raw = str(text or "")
    nfkc = unicodedata.normalize("NFKC", raw)
    contextual = _apply_contextual_observed_confusables(nfkc)
    v1 = _unicode_decimal_digits(_strip_zero_width(contextual))
    v2 = _strip_visual_noise(v1)
    v3 = _map_korean_digits(v2)
    v4 = _strip_separators(v3)
    v5 = _strip_separators_conditional_merge(v3)
    candidates = (
        ScanVariant("v0_raw", raw),
        ScanVariant("v1_nfkc_zero_width_decimal", v1),
        ScanVariant("v2_visual_noise_removed", v2),
        ScanVariant("v3_korean_digits", v3),
        ScanVariant("v4_separators_removed", v4),
        ScanVariant("v5_conditional_merge", v5),
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
    for index, pattern in enumerate(patterns):
        yield f"pattern_{index}", pattern


def _pattern_hits(pattern: Any, text: str) -> bool:
    if hasattr(pattern, "search"):
        return bool(pattern.search(text))
    if callable(pattern):
        return bool(pattern(text))
    return False


def detect_grouped(
    groups: Mapping[str, Mapping[str, Any] | Iterable[Any]],
    text: str,
    *,
    max_scan_chars: int = MAX_SCAN_CHARS,
) -> dict[str, DlpScanResult]:
    """Return the first canonical hit for each group using one variant pass."""
    value = str(text or "")
    if len(value) > max_scan_chars:
        return {"__too_long__": DlpScanResult(True, SCAN_INPUT_TOO_LONG, None, None, True)}
    if not groups:
        return {}
    pattern_groups = {group: tuple(_iter_patterns(patterns)) for group, patterns in groups.items()}
    results: dict[str, DlpScanResult] = {}
    for variant in scan_variants(value):
        for group, patterns in pattern_groups.items():
            if group in results:
                continue
            for pattern_id, pattern in patterns:
                if not _pattern_hits(pattern, variant.text):
                    continue
                reason = DLP_DETECTED_RAW if variant.variant_id == "v0_raw" else DLP_DETECTED_NORMALIZED_VARIANT
                results[group] = DlpScanResult(True, reason, variant.variant_id, pattern_id, False)
                break
        if len(results) == len(pattern_groups):
            break
    return results


def detect_all(
    patterns: Mapping[str, Any] | Iterable[Any],
    text: str,
    *,
    max_scan_chars: int = MAX_SCAN_CHARS,
) -> tuple[DlpScanResult, ...]:
    value = str(text or "")
    if len(value) > max_scan_chars:
        return (DlpScanResult(True, SCAN_INPUT_TOO_LONG, None, None, True),)
    pattern_items = tuple(_iter_patterns(patterns))
    hits: list[DlpScanResult] = []
    matched_patterns: set[str] = set()
    for variant in scan_variants(value):
        for pattern_id, pattern in pattern_items:
            if pattern_id in matched_patterns or not _pattern_hits(pattern, variant.text):
                continue
            matched_patterns.add(pattern_id)
            reason = DLP_DETECTED_RAW if variant.variant_id == "v0_raw" else DLP_DETECTED_NORMALIZED_VARIANT
            hits.append(DlpScanResult(True, reason, variant.variant_id, pattern_id, False))
    return tuple(hits)


def detect_any(
    patterns: Mapping[str, Any] | Iterable[Any],
    text: str,
    *,
    max_scan_chars: int = MAX_SCAN_CHARS,
) -> DlpScanResult:
    hits = detect_all(patterns, text, max_scan_chars=max_scan_chars)
    return hits[0] if hits else DlpScanResult(False, None, None, None, False)
