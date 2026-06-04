from __future__ import annotations

from typing import get_args

from .real_contracts import Box3RealStatus

ALLOWED_BOX3_REAL_STATUSES = set(get_args(Box3RealStatus))

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "CONTRACT_ONLY": {"ASSET_INVENTORY_PASS", "BLOCKED", "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE"},
    "ASSET_INVENTORY_PASS": {"REAL_CANDIDATE", "BLOCKED", "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE"},
    "REAL_CANDIDATE": {"PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL", "BLOCKED", "CONTRACT_ONLY"},
    "PASS_BOX3_REAL_LOCAL_AFTER_HUMAN_APPROVAL": {"BLOCKED"},
    "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE": {"ASSET_INVENTORY_PASS", "CONTRACT_ONLY", "BLOCKED"},
    "BLOCKED": {"CONTRACT_ONLY"},
}

def validate_box3_real_status(value: str) -> str:
    if value not in ALLOWED_BOX3_REAL_STATUSES:
        raise ValueError("BLOCK_BOX3_REAL_STATUS_INVALID")
    return value

def validate_box3_real_transition(previous: str, next_status: str) -> str:
    validate_box3_real_status(previous)
    validate_box3_real_status(next_status)
    if next_status not in _VALID_TRANSITIONS[previous] and next_status != previous:
        raise ValueError("BLOCK_BOX3_REAL_STATUS_TRANSITION_INVALID")
    return next_status
