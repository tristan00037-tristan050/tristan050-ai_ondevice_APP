from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .contracts import CompanyProfileRuntime
from .normalizer import normalize_account_number, normalize_holder_alias


_ACCOUNT_VERIFICATION_RE = re.compile(r"계좌\s*인증|계좌\s*확인|본인\s*확인|인증")


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


def is_account_verification(desc: str | None, amount: object) -> bool:
    try:
        value = abs(Decimal(str(amount or "0").replace(",", "").strip()))
    except (InvalidOperation, ValueError):
        return False
    if value > Decimal("1"):
        return False
    return bool(_ACCOUNT_VERIFICATION_RE.search(str(desc or "")))
