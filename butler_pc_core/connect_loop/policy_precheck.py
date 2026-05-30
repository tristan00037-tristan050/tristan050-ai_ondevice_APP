from __future__ import annotations

from typing import Literal

PolicyPrecheck = Literal["allow", "needs_review", "block"]

_ALLOWED_POLICY_PRECHECK: set[str] = {"allow", "needs_review", "block"}


def ensure_policy_precheck(value: str) -> PolicyPrecheck:
    """Validate the policy precheck enum consumed by PR-C router.

    The router is a contract consumer, not a policy engine. Invalid policy
    values are rejected before route construction so they cannot be interpreted
    as an executable allow decision.
    """
    if value not in _ALLOWED_POLICY_PRECHECK:
        raise ValueError(f"invalid policy_precheck: {value!r}")
    return value  # type: ignore[return-value]


def is_executable_policy(value: PolicyPrecheck) -> bool:
    return value == "allow"
