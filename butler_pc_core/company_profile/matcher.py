from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .contracts import CompanyProfileRuntime
from .normalizer import normalize_account_number, normalize_holder_alias


_ACCOUNT_VERIFICATION_RE = re.compile(r"계좌\s*인증|계좌\s*확인|본인\s*확인|인증")
_STRONG_INTERNAL_MEMO_RE = re.compile(
    r"내부\s*이체|본사\s*운영\s*자금|대체\s*입금|자금\s*이동|운영\s*자금\s*이체"
)
_STANDALONE_INTERNAL_COMPANY_RE = re.compile(r"(?<![가-힣])사내(?![가-힣])")
_INTERNAL_COMPANY_CONTEXT_RE = re.compile(r"자금|이체|대체|입금|계좌|보통\s*예금|운영")
_WEAK_TRANSFER_MEMO_RE = re.compile(r"계좌\s*이체|예금\s*대체|보통\s*예금|이체|송금")


def is_self_holder(counterparty: str | None, profile: CompanyProfileRuntime) -> bool:
    key = normalize_holder_alias(counterparty)
    if not key:
        return False
    known = set(profile.normalized_holder_keys) | set(profile.normalized_company_keys)
    return key in known


def is_own_account(account_no: str | None, profile: CompanyProfileRuntime) -> bool:
    normalized = normalize_account_number(account_no)
    if not normalized:
        return False
    return normalized in set(profile.normalized_account_numbers)


def is_strong_internal_memo(desc: str | None) -> bool:
    text = str(desc or "")
    if _STRONG_INTERNAL_MEMO_RE.search(text):
        return True
    if not _STANDALONE_INTERNAL_COMPANY_RE.search(text):
        return False
    return bool(_INTERNAL_COMPANY_CONTEXT_RE.search(text))


def is_weak_transfer_memo(desc: str | None) -> bool:
    return bool(_WEAK_TRANSFER_MEMO_RE.search(str(desc or "")))


def is_account_verification(desc: str | None, amount: object) -> bool:
    try:
        value = abs(Decimal(str(amount or "0").replace(",", "").strip()))
    except (InvalidOperation, ValueError):
        return False
    if value > Decimal("1"):
        return False
    return bool(_ACCOUNT_VERIFICATION_RE.search(str(desc or "")))
