"""Runtime-only DLP guard for PR-E.

The guard returns booleans only. It never returns matched raw text, file names,
local paths, tokens, or snippets.
"""
from __future__ import annotations

from typing import Any

from .persisted_safety import PersistedSafetyViolation, _dlp_scan_all, _enforce_persisted_safety


def scan_runtime_text(text: str) -> dict[str, bool]:
    scan = _dlp_scan_all(text)
    policy_violation = scan.policy_violation or scan.local_path_detected
    return {
        "passed": not (scan.pii_detected or scan.secret_detected or policy_violation),
        "pii_detected": scan.pii_detected,
        "secret_detected": scan.secret_detected,
        "policy_violation": policy_violation,
    }


def _contains_forbidden_scalar(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return _dlp_scan_all(value).any_detected


def assert_no_raw_or_secret_material(value: Any) -> None:
    """Fail closed if an object contains raw-like keys or forbidden strings."""
    try:
        _enforce_persisted_safety(value)
    except PersistedSafetyViolation as exc:
        if exc.reason_code == "RAW_FIELD_OR_SAVED_TRUE":
            raise ValueError("RAW_OR_SECRET_FIELD_FORBIDDEN") from None
        raise ValueError("RAW_OR_SECRET_VALUE_FORBIDDEN") from None
