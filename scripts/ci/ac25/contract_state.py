"""AC-25 R6 Close v4.1 contract-state truth table.

The repository-contract process exit, primary guard, failing-key set, and
parser state are independent observations.  This module is the only place
that combines them into PASS/FAIL/INVALID.  It has no default-success path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ContractOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INVALID = "INVALID"


CONTRACT_EXIT_STATE_INCONSISTENT = "CONTRACT_EXIT_STATE_INCONSISTENT"
CONTRACT_PARSE_INVALID = "CONTRACT_PARSE_INVALID"
CONTRACT_INPUT_INVALID = "CONTRACT_INPUT_INVALID"
CONTRACT_FAILED = "CONTRACT_FAILED"
NONE = "NONE"

_SPECIAL_PRIMARY = frozenset((NONE, "UNPARSED", "UNPARSED_DUPLICATE"))
_PRIMARY_RE = re.compile(r"\A[A-Za-z0-9 ._:/()\-]+\Z")
_FAILING_KEY_RE = re.compile(r"\A[A-Z][A-Z0-9_]{0,76}_OK\Z")
_PRIMARY_MAX_BYTES = 160


@dataclass(frozen=True)
class ContractStateVerdict:
    outcome: ContractOutcome
    error_code: str


def _valid_primary(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value in _SPECIAL_PRIMARY:
        return True
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        return False
    return len(encoded) <= _PRIMARY_MAX_BYTES and _PRIMARY_RE.fullmatch(value) is not None


def _valid_failing_keys(value: object) -> bool:
    if not isinstance(value, tuple):
        return False
    if list(value) != sorted(set(value)):
        return False
    return all(
        isinstance(item, str) and _FAILING_KEY_RE.fullmatch(item) is not None
        for item in value
    )


def evaluate_contract_state(
    *,
    exit_code: int,
    primary_failed_guard: str,
    failing_guard_keys: tuple[str, ...],
    parse_error_code: str,
) -> ContractStateVerdict:
    """Cross-check all four observations using the v4.1 closed truth table."""
    if (
        not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or exit_code < 0
        or not _valid_primary(primary_failed_guard)
        or not _valid_failing_keys(failing_guard_keys)
        or not isinstance(parse_error_code, str)
        or not parse_error_code
    ):
        return ContractStateVerdict(ContractOutcome.INVALID, CONTRACT_INPUT_INVALID)

    if parse_error_code != NONE:
        return ContractStateVerdict(ContractOutcome.INVALID, CONTRACT_PARSE_INVALID)

    primary_is_none = primary_failed_guard == NONE
    primary_is_unparsed = primary_failed_guard in {
        "UNPARSED",
        "UNPARSED_DUPLICATE",
    }
    has_failing_keys = bool(failing_guard_keys)

    if primary_is_unparsed:
        return ContractStateVerdict(
            ContractOutcome.INVALID,
            CONTRACT_EXIT_STATE_INCONSISTENT,
        )

    if exit_code == 0 and primary_is_none and not has_failing_keys:
        return ContractStateVerdict(ContractOutcome.PASS, NONE)

    if exit_code != 0 and (not primary_is_none or has_failing_keys):
        return ContractStateVerdict(ContractOutcome.FAIL, CONTRACT_FAILED)

    return ContractStateVerdict(
        ContractOutcome.INVALID,
        CONTRACT_EXIT_STATE_INCONSISTENT,
    )


__all__ = [
    "CONTRACT_EXIT_STATE_INCONSISTENT",
    "CONTRACT_FAILED",
    "CONTRACT_INPUT_INVALID",
    "CONTRACT_PARSE_INVALID",
    "NONE",
    "ContractOutcome",
    "ContractStateVerdict",
    "evaluate_contract_state",
]
