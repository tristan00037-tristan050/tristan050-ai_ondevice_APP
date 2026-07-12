"""Runtime-only DLP guard for PR-E.

The guard returns booleans only. It never returns matched raw text, file names,
local paths, tokens, or snippets.
"""
from __future__ import annotations

from typing import Any

from butler_pc_core.dlp.runtime import scan_runtime

from .persisted_safety import PersistedSafetyViolation, _enforce_persisted_safety


def scan_runtime_text(text: str) -> dict[str, bool]:
    scan = scan_runtime(text)
    categories = {item.category for item in scan.findings}
    pii_detected = bool(categories & {"email", "phone", "korean_rrn", "card_or_account"})
    secret_detected = "secret" in categories
    policy_violation = scan.policy_violation or "local_path" in categories
    return {
        "passed": not (pii_detected or secret_detected or policy_violation),
        "pii_detected": pii_detected,
        "secret_detected": secret_detected,
        "policy_violation": policy_violation,
    }


def _contains_forbidden_scalar(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return scan_runtime(value).any_detected


def assert_no_raw_or_secret_material(value: Any) -> None:
    """Fail closed if an object contains raw-like keys or forbidden strings."""
    try:
        _enforce_persisted_safety(value)
    except PersistedSafetyViolation as exc:
        if exc.reason_code == "RAW_FIELD_OR_SAVED_TRUE":
            raise ValueError("RAW_OR_SECRET_FIELD_FORBIDDEN") from None
        raise ValueError("RAW_OR_SECRET_VALUE_FORBIDDEN") from None
