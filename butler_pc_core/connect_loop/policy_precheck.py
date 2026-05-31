"""Policy precheck helpers for Box1 router fail-closed behavior."""

from __future__ import annotations

import re
from typing import Literal

PolicyPrecheck = Literal["allow", "needs_review", "block"]

_POLICY_VALUES = {"allow", "needs_review", "block"}
_REASON_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def ensure_policy_precheck(value: str) -> PolicyPrecheck:
    if value not in _POLICY_VALUES:
        raise ValueError("INVALID_POLICY_PRECHECK")
    return value  # type: ignore[return-value]


def is_route_allowed(value: PolicyPrecheck) -> bool:
    return value == "allow"


def policy_reason_code(value: PolicyPrecheck, supplied: str | None = None) -> str:
    if supplied and _REASON_RE.fullmatch(supplied):
        return supplied
    if value == "needs_review":
        return "POLICY_NEEDS_REVIEW"
    if value == "block":
        return "POLICY_BLOCK"
    return "INTENT_KEYWORD_MATCH"
