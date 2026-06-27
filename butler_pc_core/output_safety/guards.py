"""Deterministic output guards for safe general chat.

These guards are deliberately simple and local. They do not ask another model
to judge a model output, because the free-chat safety path must be fail-closed,
fast, and deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


SAFE_FIXED_TEXT = (
    "현재 답변이 Butler의 안전 기준과 맞지 않아 표시하지 않았습니다.\n"
    "Butler는 회사 데이터를 기기 밖으로 보내지 않는 원칙으로 동작합니다.\n"
    "회사 내부 사실이나 수치는 확인된 근거가 있을 때만 답변합니다."
)

PRODUCT_PRIVACY_TEXT = (
    "Butler는 회사 데이터를 기기 밖으로 보내지 않고, 로컬 기기와\n"
    "허용된 사내 환경 안에서 처리하는 온디바이스 AI 업무 OS입니다."
)

CONFIRM_REQUIRED_TEXT = (
    "확인 필요: 회사 내부 사실, 금액, 날짜, 계정과목은 확인된 근거가 있을 때만 답변할 수 있습니다."
)


class GuardAction(str, Enum):
    ALLOW = "allow"
    REPLACE = "replace"
    BLOCK = "block"


@dataclass(frozen=True)
class GuardContext:
    route: str = "general_chat"
    profile: str = "free_general_chat"
    grounded_evidence: bool = False


@dataclass(frozen=True)
class GuardVerdict:
    action: GuardAction
    code: str = "OK"
    replacement_text: str | None = None
    details: dict[str, object] = field(default_factory=dict)

    @property
    def allowed_text(self) -> str | None:
        if self.action == GuardAction.REPLACE:
            return self.replacement_text or SAFE_FIXED_TEXT
        return None


_SYSTEM_LEAK_PATTERNS = (
    re.compile(r"<\|im_(?:start|end)\|>", re.IGNORECASE),
    re.compile(r"\b(system|developer)\s+prompt\b", re.IGNORECASE),
    re.compile(r"시스템\s*프롬프트|개발자\s*지침|내부\s*지침|ChatML", re.IGNORECASE),
    re.compile(r"당신은\s+유능한\s+사무\s+보조\s+AI입니다"),
)

_PRIVACY_REVERSAL_PATTERNS = (
    re.compile(r"기기\s*밖(?:으로)?\s*보냅니다"),
    re.compile(r"외부\s*(?:서버|클라우드)(?:로|에)\s*(?:전송|보냅니다|업로드)"),
    re.compile(r"회사\s*데이터를\s*외부(?:로|에)\s*(?:전송|보냅니다|업로드)"),
    re.compile(r"기기\s*밖(?:으로)?\s*(?:보낼\s*수|전송할\s*수|보낼|전송|업로드)", re.IGNORECASE),
    re.compile(r"(?:외부|밖)(?:로|으로|에)\s*(?:보낼\s*수|전송할\s*수|업로드할\s*수)", re.IGNORECASE),
    re.compile(r"데이터를\s*(?:외부|밖)(?:로|으로|에).{0,16}(?:보낼|전송|업로드|가능)", re.IGNORECASE),
)

_PRIVACY_NEGATION_PATTERNS = (
    re.compile(
        r"(?:기기\s*밖|외부|밖|데이터를\s*(?:외부|밖)).{0,32}"
        r"(?:보낼|전송|업로드|가능).{0,12}(?:없|않|금지|차단)",
        re.IGNORECASE,
    ),
)

_ACCOUNTING_OUTPUT_PATTERNS = (
    re.compile(r"계정과목|분개|차변|대변|손익계산서|재무상태표"),
    re.compile(r"\d[\d,]*(?:\s?원|\s?만원|\s?억원)"),
    re.compile(r"\b(?:매출|비용|입금|출금)\b.*\d"),
)

_UNSUPPORTED_DATE_PATTERNS = (
    re.compile(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일"),
    re.compile(r"\d{4}-\d{1,2}-\d{1,2}"),
)

_UNSUPPORTED_NUMBER_PATTERNS = (
    re.compile(r"\d[\d,]*(?:\s?(?:만|억|조))?\s*(?:달러|USD|\$)", re.IGNORECASE),
    re.compile(r"\d[\d,]*\s*(?:개|톤|kg|건)\s*/\s*(?:일|월|년)", re.IGNORECASE),
    re.compile(r"\d[\d,]*(?:\s?(?:만|억|조))?\s*(?:달러|원|만원|억원)\s*/\s*(?:일|월|년)", re.IGNORECASE),
    re.compile(
        r"(?:재고량|수출액|생산량|매출액|수입액)\s*(?:[:：]|[은는이가])?\s*"
        r"\d[\d,]*(?:\s?(?:개|톤|kg|건|달러|USD|\$|원|만원|억원))?",
        re.IGNORECASE,
    ),
)

_SELF_JUDGMENT_PATTERNS = (re.compile(r"사실값|임의값|otherwise", re.IGNORECASE),)

_SECRET_ECHO_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY"),
    re.compile(r"/Users/[^\s]+"),
    re.compile(r"[A-Za-z]:\\[^\s]+"),
)

_ALLOWED_LATIN_TERMS = {"butler", "ai", "os", "llm", "qwen", "qwen3"}


class SafeChatGuard:
    """Profile-aware final text guard for free/general chat."""

    def evaluate(self, text: str, context: GuardContext | None = None) -> GuardVerdict:
        ctx = context or GuardContext()
        normalized = text or ""

        if self._matches(normalized, _SECRET_ECHO_PATTERNS):
            return GuardVerdict(GuardAction.REPLACE, "RAW_SECRET_ECHO_BLOCKED", SAFE_FIXED_TEXT)

        if self._matches(normalized, _SYSTEM_LEAK_PATTERNS):
            return GuardVerdict(GuardAction.REPLACE, "SYSTEM_PROMPT_LEAK_BLOCKED", SAFE_FIXED_TEXT)

        if self._has_privacy_reversal(normalized):
            return GuardVerdict(GuardAction.REPLACE, "DEVICE_PRIVACY_INVARIANT_REPLACED", SAFE_FIXED_TEXT)

        if ctx.profile == "free_general_chat":
            if self._matches(normalized, _ACCOUNTING_OUTPUT_PATTERNS):
                return GuardVerdict(
                    GuardAction.REPLACE,
                    "ROUTE_OUTPUT_MISMATCH_BLOCKED",
                    CONFIRM_REQUIRED_TEXT,
                    {"unsupported_numbers": self._count_unsupported_numbers(normalized)},
                )
            if not ctx.grounded_evidence and self._matches(normalized, _UNSUPPORTED_DATE_PATTERNS):
                return GuardVerdict(
                    GuardAction.REPLACE,
                    "UNSUPPORTED_NUMBER_REPLACED",
                    CONFIRM_REQUIRED_TEXT,
                    {"unsupported_numbers": self._count_unsupported_numbers(normalized)},
                )
            if not ctx.grounded_evidence and self._matches(normalized, _UNSUPPORTED_NUMBER_PATTERNS):
                return GuardVerdict(
                    GuardAction.REPLACE,
                    "UNSUPPORTED_NUMBER_REPLACED",
                    CONFIRM_REQUIRED_TEXT,
                    {"unsupported_numbers": self._count_unsupported_numbers(normalized)},
                )
            if self._matches(normalized, _SELF_JUDGMENT_PATTERNS):
                return GuardVerdict(GuardAction.REPLACE, "SELF_JUDGMENT_LEAK_BLOCKED", SAFE_FIXED_TEXT)
            if _has_language_mix(normalized):
                return GuardVerdict(GuardAction.REPLACE, "LANGUAGE_MIX_BLOCKED", SAFE_FIXED_TEXT)

        return GuardVerdict(
            GuardAction.ALLOW,
            "OK",
            None,
            {"unsupported_numbers": self._count_unsupported_numbers(normalized)},
        )

    @staticmethod
    def _matches(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
        return any(pattern.search(text) for pattern in patterns)

    @classmethod
    def _has_privacy_reversal(cls, text: str) -> bool:
        return cls._matches(text, _PRIVACY_REVERSAL_PATTERNS) and not cls._matches(
            text, _PRIVACY_NEGATION_PATTERNS
        )

    @staticmethod
    def _count_unsupported_numbers(text: str) -> int:
        amount_hits = len(re.findall(r"\d[\d,]*(?:\s?원|\s?만원|\s?억원)", text))
        date_hits = len(re.findall(r"\d{4}(?:년|-)\s?\d{1,2}(?:월|-)\s?\d{1,2}", text))
        unsupported_hits = sum(len(pattern.findall(text)) for pattern in _UNSUPPORTED_NUMBER_PATTERNS)
        return amount_hits + date_hits + unsupported_hits


def _has_language_mix(text: str) -> bool:
    hangul = len(re.findall(r"[가-힣]", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = [
        word
        for word in re.findall(r"[A-Za-z][A-Za-z0-9]{3,}", text)
        if word.casefold() not in _ALLOWED_LATIN_TERMS
    ]
    if hangul == 0:
        return False
    return cjk >= 2 or len(latin) >= 3
