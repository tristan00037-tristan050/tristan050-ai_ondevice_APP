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
# \ud1a0\ud070 \ub0b4\ubd80 \uad6c\ubd84\uc790(\uacc4\uc88c/\uce74\ub4dc \ubc88\ud638 \uc704\uc7a5\uc5d0 \uc4f0\uc774\ub294 . - _ / : \ubc0f \uac01\uc885 \ub300\uc2dc)\ub9cc \uc81c\uac70\ud55c\ub2e4.
# \uacf5\ubc31\ub958(\s)\ub294 \uc5ec\uae30 \ud3ec\ud568\ud558\uc9c0 \uc54a\ub294\ub2e4 \u2014 \uacf5\ubc31 \uacbd\uacc4\ub97c \uc9c0\uc6cc \ubb34\uad00\ud55c \ud544\ub4dc(\ub0a0\uc9dc\u00b7\uc2dc\uac01\u00b7\ub2e8\uc5b4)\uac00
# \ud558\ub098\uc758 \uae34 \uc22b\uc790\uc5f4\ub85c \ubcd1\ud569\ub418\ub294 \uac83\uc744 \ub9c9\uae30 \uc704\ud568(\uc608: "2026-07-04 12:30" \u2192 "202607041230" \uc624\ud0d0).
_INTRA_TOKEN_SEPARATOR_RE = re.compile(r"[.\-_/:\u058a\u05be\u1400\u1806\u2010-\u2015\u2e17\u2e1a\u2e3a\u2e3b\u30a0\ufe31\ufe32\ufe58\ufe63\uff0d]+")
_NUMERIC_SEPARATOR_RE = re.compile(
    r"(?<=\d)[.\-_/:\u058a\u05be\u1400\u1806\u2010-\u2015\u2e17\u2e1a\u2e3a\u2e3b\u30a0\ufe31\ufe32\ufe58\ufe63\uff0d]+(?=\d)"
)
_WHITESPACE_RE = re.compile(r"\s+")
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
_KOREAN_DIGIT_UNIT_PATTERN = r"(?:아홉|여덟|일곱|여섯|다섯|하나|둘|셋|넷|[영공빵일이삼사오육륙칠팔구])"
_KOREAN_DIGIT_UNIT_RE = re.compile(_KOREAN_DIGIT_UNIT_PATTERN)
_KOREAN_DIGIT_RUN_RE = re.compile(
    rf"{_KOREAN_DIGIT_UNIT_PATTERN}(?:[\s.\-_/\:\u2010-\u2015\uff0d]*{_KOREAN_DIGIT_UNIT_PATTERN}){{3,}}"
)
_CONFUSABLE_CONTEXT_RE = re.compile(
    r"(?i)(계좌|카드|전화|연락|휴대폰|주민|주민등록|account|acct|card|phone|tel|mobile|rrn|resident)"
)
# Production mappings are admitted only from a measured corpus allowlist. The
# handoff contains no raw corpus, so the default remains intentionally empty.
_OBSERVED_CONFUSABLE_DIGITS: dict[str, str] = {}
_FORBIDDEN_ASCII_CONFUSABLES = frozenset({"O", "I", "l"})


def _map_observed_digit_confusables(text: str, mapping: Mapping[str, str] | None = None) -> str:
    """Map measured non-ASCII digit confusables only inside a narrow context.

    A candidate window must contain at least six decimal-like digits within 24
    characters, or at least four when a DLP context word is present. ASCII
    O/I/l are never accepted as digit aliases.
    """
    allowed = {
        source: target
        for source, target in (mapping or _OBSERVED_CONFUSABLE_DIGITS).items()
        if source not in _FORBIDDEN_ASCII_CONFUSABLES
        and not source.isascii()
        and target in "0123456789"
    }
    if not allowed:
        return text

    chars = list(text)
    for index, char in enumerate(chars):
        if char not in allowed:
            continue
        start = max(0, index - 12)
        end = min(len(chars), index + 12)
        window = "".join(chars[start:end])
        digit_count = sum(item.isdecimal() or item in allowed for item in window)
        has_context = bool(_CONFUSABLE_CONTEXT_RE.search(window))
        if digit_count >= 6 or (has_context and digit_count >= 4):
            chars[index] = allowed[char]
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
    def replace_candidate(match: re.Match[str]) -> str:
        source_count = len(_KOREAN_DIGIT_UNIT_RE.findall(match.group(0)))
        window = text[max(0, match.start() - 24) : min(len(text), match.end() + 24)]
        if source_count < 6 and not (_CONFUSABLE_CONTEXT_RE.search(window) and source_count >= 4):
            return match.group(0)
        mapped = match.group(0)
        for source, target in _KOREAN_DIGIT_TOKENS:
            mapped = mapped.replace(source, target)
        return mapped.translate(_KOREAN_DIGIT_CHARS)

    return _KOREAN_DIGIT_RUN_RE.sub(replace_candidate, text)


def _strip_separators(text: str) -> str:
    # 숫자 양쪽의 구분자만 제거한다. 일반 문장 부호와 경로 경계는 보존한다.
    return _NUMERIC_SEPARATOR_RE.sub("", text)


def _strip_separators_conditional_merge(text: str) -> str:
    """v5: 공백으로 나뉜 '원시 숫자 토큰'끼리만 병합한다.

    구조화된 토큰(내부에 -._/: 등 구분자가 있었던 토큰)은 병합 경계로 작동한다.
    이렇게 하면 '110 234 567890'(원시 토큰 3개)은 병합되어 탐지되고,
    '2026-07-04 12:30'(둘 다 구조화된 토큰)은 병합되지 않아 오탐이 없다.
    새 정규식·날짜 판별 없이 기존 신호(_INTRA_TOKEN_SEPARATOR_RE 매치 여부)만 사용한다.
    """
    tokens = _WHITESPACE_RE.split(text)
    groups: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        stripped = _NUMERIC_SEPARATOR_RE.sub("", token)
        is_structured = stripped != token  # 숫자 사이에 구분자가 있었으면 구조화된 토큰
        if is_structured:
            if current:
                groups.append(current)
                current = []
            groups.append([stripped])  # 구조화된 토큰은 단독 그룹(경계)
        elif stripped.isdecimal():
            current.append(stripped)   # 원시 토큰은 이어붙임 후보
        else:
            if current:
                groups.append(current)
                current = []
            groups.append([stripped])
    if current:
        groups.append(current)
    return " ".join("".join(g) for g in groups)


def _has_runtime_numeric_candidate(text: str) -> bool:
    for token in _WHITESPACE_RE.split(text):
        compact = _NUMERIC_SEPARATOR_RE.sub("", token)
        if compact.isdecimal() and len(compact) >= 10:
            return True
        if _NUMERIC_SEPARATOR_RE.search(token) and sum(char.isdecimal() for char in token) >= 10:
            return True

    digit_run = 0
    for token in _WHITESPACE_RE.split(text):
        if token.isdecimal():
            digit_run += len(token)
            if digit_run >= 10:
                return True
        else:
            digit_run = 0
    return False


def scan_variants(text: str, *, runtime_optimized: bool = False) -> list[ScanVariant]:
    raw = str(text or "")
    normalized = unicodedata.normalize("NFKC", raw)
    normalized = _map_observed_digit_confusables(normalized)
    v1 = _unicode_decimal_digits(_strip_zero_width(normalized))
    v2 = _strip_visual_noise(v1)
    v3 = _map_korean_digits(v2)
    candidates: tuple[ScanVariant, ...] = (
        ScanVariant("v0_raw", raw),
        ScanVariant("v1_nfkc_zero_width_decimal", v1),
        ScanVariant("v2_visual_noise_removed", v2),
        ScanVariant("v3_korean_digits", v3),
    )
    if not runtime_optimized or _has_runtime_numeric_candidate(v3):
        candidates += (
            ScanVariant("v4_separators_removed", _strip_separators(v3)),
            ScanVariant("v5_conditional_merge", _strip_separators_conditional_merge(v3)),
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


def detect_any_variants(patterns: Mapping[str, Any] | Iterable[Any], variants: Iterable[ScanVariant]) -> DlpScanResult:
    """Scan a precomputed variant set without repeating normalization work."""
    for variant in variants:
        for pattern_id, pattern in _iter_patterns(patterns):
            if not _pattern_hits(pattern, variant.text):
                continue
            reason_code = DLP_DETECTED_RAW if variant.variant_id == "v0_raw" else DLP_DETECTED_NORMALIZED_VARIANT
            return DlpScanResult(True, reason_code, variant.variant_id, pattern_id, False)
    return DlpScanResult(False, None, None, None, False)


def detect_any(patterns: Mapping[str, Any] | Iterable[Any], text: str, *, max_scan_chars: int = MAX_SCAN_CHARS) -> DlpScanResult:
    value = str(text or "")
    if len(value) > max_scan_chars:
        return DlpScanResult(True, SCAN_INPUT_TOO_LONG, None, None, True)
    return detect_any_variants(patterns, scan_variants(value))
