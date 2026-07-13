"""Raw-zero DLP scan normalization for connect-loop ingress points."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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
_CONFUSABLE_SCHEMA_VERSION = "butler.dlp.observed_confusables.v1"
_CONFUSABLE_PATH = Path(__file__).with_name("observed_confusable_codepoints.v1.json")
_CONFUSABLE_EXACT_KEYS = {"schema_version", "corpus_digest", "mappings", "raw_text_logged", "status"}
_CONFUSABLE_MAPPING_KEYS = {"codepoint", "ascii_digit", "categories", "count"}
_ALLOWED_CONFUSABLE_CATEGORIES = frozenset({"phone", "korean_rrn", "card_or_account"})
_FORBIDDEN_ASCII_CONFUSABLE_CODEPOINTS = frozenset({
    ord("O"), ord("o"), ord("I"), ord("i"), ord("L"), ord("l"),
})
_CONFUSABLE_CONTEXT_TERMS: dict[str, tuple[str, ...]] = {
    "phone": ("전화", "연락", "휴대폰", "phone", "tel", "mobile"),
    "korean_rrn": ("주민", "주민등록", "rrn", "resident"),
    "card_or_account": ("계좌", "입금", "상환", "예금", "account", "acct", "카드", "card"),
}
ObservedConfusableMapping = tuple[str, str, tuple[str, ...]]


def _already_normalized_to_digit(char: str) -> bool:
    normalized = unicodedata.normalize("NFKC", char)
    try:
        converted = str(unicodedata.decimal(normalized)) if len(normalized) == 1 else normalized
    except (TypeError, ValueError):
        converted = normalized
    return len(converted) == 1 and converted.isascii() and converted.isdigit()


def _parse_observed_confusable_asset(data: Any) -> tuple[ObservedConfusableMapping, ...]:
    if not isinstance(data, dict) or set(data) != _CONFUSABLE_EXACT_KEYS:
        raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
    if data["schema_version"] != _CONFUSABLE_SCHEMA_VERSION or data["raw_text_logged"] is not False:
        raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
    status = data["status"]
    corpus_digest = data["corpus_digest"]
    rows = data["mappings"]
    if not isinstance(rows, list):
        raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
    if status == "GROUP_A_CORPUS_PROBE_PENDING":
        if corpus_digest is not None or rows:
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
    elif status == "MEASURED":
        if not isinstance(corpus_digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", corpus_digest):
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
    else:
        raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")

    parsed: list[ObservedConfusableMapping] = []
    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != _CONFUSABLE_MAPPING_KEYS:
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
        codepoint = row["codepoint"]
        digit = row["ascii_digit"]
        categories = row["categories"]
        count = row["count"]
        if not isinstance(codepoint, str) or not re.fullmatch(r"U\+[0-9A-F]{4,6}", codepoint):
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
        value = int(codepoint[2:], 16)
        if value <= 0x7F or value in seen or value in _FORBIDDEN_ASCII_CONFUSABLE_CODEPOINTS:
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
        if not isinstance(digit, str) or not re.fullmatch(r"[0-9]", digit):
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
        if not isinstance(categories, list) or not categories:
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
        category_tuple = tuple(sorted(set(categories)))
        if not set(category_tuple) <= _ALLOWED_CONFUSABLE_CATEGORIES:
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
        char = chr(value)
        if _already_normalized_to_digit(char):
            raise ValueError("CONFUSABLE_ALLOWLIST_INVALID")
        seen.add(value)
        parsed.append((char, digit, category_tuple))
    return tuple(parsed)


@lru_cache(maxsize=4)
def load_observed_confusable_mappings(path_text: str | None = None) -> tuple[ObservedConfusableMapping, ...]:
    """Load a codepoint-only allowlist; malformed or absent assets disable only this optional mapping."""
    path = Path(path_text) if path_text else _CONFUSABLE_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _parse_observed_confusable_asset(data)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError):
        return ()


def _has_confusable_context(text: str, categories: Sequence[str], start: int, end: int) -> bool:
    context = text[max(0, start - 24) : min(len(text), end + 24)].casefold()
    return any(term in context for category in categories for term in _CONFUSABLE_CONTEXT_TERMS[category])


def _apply_observed_confusables_contextual(
    text: str,
    mappings: Sequence[ObservedConfusableMapping],
) -> str:
    if not text or not mappings:
        return text
    by_source = {source: (digit, categories) for source, digit, categories in mappings}
    output = list(text)
    for index, char in enumerate(text):
        mapped = by_source.get(char)
        if mapped is None:
            continue
        digit, categories = mapped
        start = max(0, index - 12)
        end = min(len(text), start + 24)
        decimal_count = sum(item.isdecimal() for item in text[start:end])
        if decimal_count >= 6 or (decimal_count >= 4 and _has_confusable_context(text, categories, start, end)):
            output[index] = digit
    return "".join(output)


def _map_observed_digit_confusables(text: str, mapping: Mapping[str, str] | None = None) -> str:
    """Map measured non-ASCII digit confusables only inside a narrow context.

    A candidate window must contain at least six decimal-like digits within 24
    characters, or at least four when a DLP context word is present. ASCII
    O/I/l are never accepted as digit aliases.
    """
    if mapping is None:
        mappings = load_observed_confusable_mappings()
    else:
        mappings = tuple(
            (source, target, tuple(_CONFUSABLE_CONTEXT_TERMS))
            for source, target in mapping.items()
            if not source.isascii() and target in "0123456789"
        )
    return _apply_observed_confusables_contextual(text, mappings)


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


def _is_standalone_date_or_time_token(token: str) -> bool:
    """Return True for complete calendar/time tokens that must remain boundaries."""
    parts = _INTRA_TOKEN_SEPARATOR_RE.split(token)
    if not parts or any(not part.isdecimal() for part in parts):
        return False

    values = tuple(int(part) for part in parts)
    lengths = tuple(len(part) for part in parts)
    if ":" in token:
        if len(parts) not in {2, 3} or lengths not in {(1, 2), (2, 2), (1, 2, 2), (2, 2, 2)}:
            return False
        hour, minute, *seconds = values
        return 0 <= hour <= 23 and 0 <= minute <= 59 and (not seconds or 0 <= seconds[0] <= 59)

    if len(parts) != 3:
        return False
    if lengths[0] == 4 and lengths[1] in {1, 2} and lengths[2] in {1, 2}:
        _year, month, day = values
        return 1 <= month <= 12 and 1 <= day <= 31
    if lengths[2] == 4 and lengths[0] in {1, 2} and lengths[1] in {1, 2}:
        day, month, _year = values
        return 1 <= month <= 12 and 1 <= day <= 31
    return False


def _mergeable_structured_numeric_token(token: str) -> str | None:
    """Return compact digits only for structured account/card candidates."""
    stripped = _NUMERIC_SEPARATOR_RE.sub("", token)
    if stripped == token or not stripped.isdecimal() or _is_standalone_date_or_time_token(token):
        return None
    return stripped


def _strip_separators_conditional_merge(text: str) -> str:
    """v5: 공백으로 나뉜 '원시 숫자 토큰'끼리만 병합한다.

    구조화된 토큰(내부에 -._/: 등 구분자가 있었던 토큰)은 병합 경계로 작동한다.
    이렇게 하면 '110 234 567890'(원시 토큰 3개)은 병합되어 탐지되고,
    '2026-07-04 12:30'(둘 다 구조화된 토큰)은 병합되지 않아 오탐이 없다.
    새 정규식·날짜 판별 없이 기존 신호(_INTRA_TOKEN_SEPARATOR_RE 매치 여부)만 사용한다.

    단, 계좌/카드 문맥 단어(_CONFUSABLE_CONTEXT_TERMS["card_or_account"])가 텍스트에
    있을 때만 병합을 완화하여 공백+하이픈 혼합 계좌도 탐지한다:
      · 공백으로 분리된 순수 구분자 토큰("-" 등)은 병합 경계가 아니라 건너뛴다
        ('입금 계좌 110 - 234 - 567890' → '...110234567890').
      · 내부 구분자를 제거하면 순수 숫자가 되는 구조화 토큰도 이어붙임 후보로 포함한다
        ('계좌 110-234 567890' → '계좌 110234567890').
    문맥이 없으면 완화하지 않으므로(문맥 게이트) 날짜·시각 오탐은 0으로 유지된다.
    여기서도 새 정규식·날짜 판별은 쓰지 않고 기존 문맥 단어 목록만 사용한다.
    """
    account_context = any(
        term in text.casefold() for term in _CONFUSABLE_CONTEXT_TERMS["card_or_account"]
    )
    tokens = _WHITESPACE_RE.split(text)
    groups: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if account_context and token and not _INTRA_TOKEN_SEPARATOR_RE.sub("", token):
            # 계좌 문맥 하에서만: 공백으로 분리된 순수 구분자 토큰("-" 등)은 병합 경계가
            # 아니라 건너뛴다. 문맥이 없으면 아래 원래 경로로 떨어져 경계로 작동한다.
            continue
        stripped = _NUMERIC_SEPARATOR_RE.sub("", token)
        is_structured = stripped != token  # 숫자 사이에 구분자가 있었으면 구조화된 토큰
        if is_structured:
            mergeable = _mergeable_structured_numeric_token(token)
            if account_context and mergeable is not None:
                # 계좌 문맥 하에서만: 내부 구분자 제거 후 순수 숫자인 구조화 토큰도
                # 이어붙임 후보로 포함한다. 날짜·시각 토큰은 항상 경계로 유지한다.
                current.append(mergeable)
                continue
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

    # 계좌/카드 문맥 하에서는 v5 조건부 병합이 공백+하이픈 혼합 계좌를 하나의 숫자열로
    # 합치므로, 이 런타임 사전 게이트도 v5와 동일한 완화 규칙(순수 구분자 토큰은 건너뛰고,
    # 내부 구분자 제거 후 순수 숫자가 되는 구조화 토큰은 이어 세기)으로 후보를 인정해야
    # v5가 실제로 계산·탐지된다. 문맥이 없으면 완화하지 않아 날짜·시각 오탐은 0으로 유지된다.
    # 새 정규식·날짜 판별 없이 기존 신호·문맥 단어 목록만 사용한다.
    if any(term in text.casefold() for term in _CONFUSABLE_CONTEXT_TERMS["card_or_account"]):
        digit_run = 0
        for token in _WHITESPACE_RE.split(text):
            if token and not _INTRA_TOKEN_SEPARATOR_RE.sub("", token):
                continue  # 순수 구분자 토큰("-" 등)은 병합 경계가 아니다.
            stripped = token if token.isdecimal() else _mergeable_structured_numeric_token(token)
            if stripped is not None:
                digit_run += len(stripped)
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
