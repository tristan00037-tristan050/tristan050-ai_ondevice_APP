from __future__ import annotations

import re
import unicodedata


_CORP_PREFIX_RE = re.compile(r"^(?:주식회사|\(주\)|주\))")
_TRAILING_PAREN_SUFFIX_RE = re.compile(r"\([^)]*$|\([^)]*\)$")
_SEPARATORS_RE = re.compile(r"[\s\u3000\xa0·.,/_\\-]+")


def _nfkc(value: str | None) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def normalize_holder_alias(value: str | None) -> str:
    text = _nfkc(value)
    text = text.replace("㈜", "(주)")
    text = _CORP_PREFIX_RE.sub("", text)
    text = _TRAILING_PAREN_SUFFIX_RE.sub("", text).strip()
    text = _SEPARATORS_RE.sub("", text)
    return text.lower()


def normalize_company_alias(value: str | None) -> str:
    return normalize_holder_alias(value)


def normalize_account_number(value: str | None) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def unique_normalized(values: list[str], normalizer) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        key = normalizer(value)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def holder_alias_hint(value: str | None) -> str | None:
    text = _nfkc(value)
    if not text:
        return None
    if len(text) <= 8:
        return text[: max(1, len(text) - 1)] + "…"
    return text[:8] + "…"


def account_number_hint(value: str | None) -> str | None:
    digits = normalize_account_number(value)
    if not digits:
        return None
    tail = digits[-3:]
    return "***-******-**-" + tail
