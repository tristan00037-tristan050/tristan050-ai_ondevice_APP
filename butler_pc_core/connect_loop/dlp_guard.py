"""Runtime-only DLP guard backed by the public Butler DLP facade."""
from __future__ import annotations

from typing import Any

from butler_pc_core.dlp.runtime import scan_runtime
from .persisted_safety import PersistedSafetyViolation, _enforce_persisted_safety


def scan_runtime_text(text: str) -> dict[str, bool]:
    scan = scan_runtime(text)
    policy_violation = scan.policy_violation or scan.local_path_detected or scan.too_long
    return {
        "passed": not (scan.pii_detected or scan.secret_detected or policy_violation),
        "pii_detected": scan.pii_detected,
        "secret_detected": scan.secret_detected,
        "policy_violation": policy_violation,
    }


def _contains_forbidden_scalar(value: Any) -> bool:
    return isinstance(value, str) and scan_runtime(value).any_detected


def assert_no_raw_or_secret_material(value: Any) -> None:
    try:
        _enforce_persisted_safety(value)
    except PersistedSafetyViolation as exc:
        if exc.reason_code == "RAW_FIELD_OR_SAVED_TRUE":
            raise ValueError("RAW_OR_SECRET_FIELD_FORBIDDEN") from None
        raise ValueError("RAW_OR_SECRET_VALUE_FORBIDDEN") from None
