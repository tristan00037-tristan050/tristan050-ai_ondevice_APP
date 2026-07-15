from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .errors import PolicyLoadError

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_KRW_RE = re.compile(r"^[+-]?(?:0|[1-9][0-9]{0,18}|[1-9][0-9]{0,15}(?:,[0-9]{3}){1,6})(?:\.[0-9]+)?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Money:
    currency: str
    minor_units: int
    source_text_sha256: str

    def __post_init__(self) -> None:
        if not _CURRENCY_RE.fullmatch(self.currency):
            raise PolicyLoadError("MONEY", "INVALID_CURRENCY")
        if not isinstance(self.minor_units, int) or isinstance(self.minor_units, bool):
            raise PolicyLoadError("MONEY", "NOT_INTEGER_MINOR_UNITS")
        if not _SHA256_RE.fullmatch(self.source_text_sha256):
            raise PolicyLoadError("MONEY", "INVALID_SOURCE_DIGEST")


def source_text_sha256(text: str) -> str:
    if not isinstance(text, str):
        raise PolicyLoadError("MONEY", "SOURCE_TEXT_NOT_STRING")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_krw(text: str, *, digest: str) -> Money:
    if not isinstance(text, str):
        raise PolicyLoadError("MONEY", "SOURCE_TEXT_NOT_STRING")
    if len(text.encode("utf-8")) > 256:
        raise PolicyLoadError("MONEY", "SOURCE_TEXT_TOO_LARGE")
    if digest != source_text_sha256(text):
        raise PolicyLoadError("MONEY", "SOURCE_DIGEST_MISMATCH")
    normalized = text.strip()
    if not _KRW_RE.fullmatch(normalized):
        raise PolicyLoadError("MONEY", "INVALID_KRW_TEXT")
    try:
        amount = Decimal(normalized.replace(",", ""))
    except InvalidOperation as exc:
        raise PolicyLoadError("MONEY", "INVALID_KRW_TEXT") from exc
    if not amount.is_finite():
        raise PolicyLoadError("MONEY", "NONFINITE_AMOUNT")
    if amount != amount.to_integral_value():
        raise PolicyLoadError("MONEY", "KRW_HAS_FRACTION")
    minor_units = int(amount)
    if abs(minor_units) > 10**18:
        raise PolicyLoadError("MONEY", "AMOUNT_OUT_OF_RANGE")
    return Money(currency="KRW", minor_units=minor_units, source_text_sha256=digest)
