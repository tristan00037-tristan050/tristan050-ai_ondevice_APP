from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


PII_PATTERNS = [
    (r"\b01[0-9]-\d{3,4}-\d{4}\b", "[PHONE]"),
    (r"[\w.+-]+@[\w.-]+\.\w+", "[EMAIL]"),
    (r"\b\d{6}-[1-4]\d{6}\b", "[JUMIN]"),
    (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "[CARD]"),
    (r"\b\d{3}-\d{2}-\d{5}\b", "[BIZ_NUM]"),
]


@dataclass
class CleanResult:
    text: str
    is_korean: bool
    korean_ratio: float
    pii_count: int
    original_length: int
    cleaned_length: int
    passed: bool
    reject_reason: str = ""


class DataCleaner:
    def __init__(
        self,
        min_korean_ratio: float = 0.5,
        min_length: int = 20,
        max_length: int = 8192,
    ):
        self.min_korean_ratio = float(min_korean_ratio)
        self.min_length = int(min_length)
        self.max_length = int(max_length)

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFC", text or "")
        normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @staticmethod
    def _mask_pii(text: str) -> tuple[str, int]:
        count = 0
        result = text
        for pattern, replacement in PII_PATTERNS:
            result, n = re.subn(pattern, replacement, result)
            count += n
        return result, count

    @staticmethod
    def _korean_ratio(text: str) -> float:
        visible = [c for c in text if not c.isspace()]
        if not visible:
            return 0.0
        korean = sum(1 for c in visible if "가" <= c <= "힣")
        return korean / len(visible)

    def clean(self, text: str) -> CleanResult:
        original_length = len(text or "")
        normalized = self._normalize(text or "")
        masked, pii_count = self._mask_pii(normalized)
        cleaned_length = len(masked)
        korean_ratio = self._korean_ratio(masked)
        is_korean = korean_ratio >= self.min_korean_ratio

        length_ok = self.min_length <= cleaned_length <= self.max_length
        loss_ratio = 1.0 - (cleaned_length / max(original_length, 1))
        loss_ok = loss_ratio < 0.8

        reject_reason = ""
        if not is_korean:
            reject_reason = f"korean_ratio_low:{korean_ratio:.2f}"
        elif not length_ok:
            reject_reason = f"length_out_of_range:{cleaned_length}"
        elif not loss_ok:
            reject_reason = "excessive_loss_after_clean"

        return CleanResult(
            text=masked,
            is_korean=is_korean,
            korean_ratio=round(korean_ratio, 4),
            pii_count=pii_count,
            original_length=original_length,
            cleaned_length=cleaned_length,
            passed=(reject_reason == ""),
            reject_reason=reject_reason,
        )
