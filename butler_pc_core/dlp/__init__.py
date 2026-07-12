"""Public runtime DLP facade.

Application features must import DLP behavior from this package instead of
reaching into connect-loop persistence internals.
"""

from .runtime import (
    SAFE_SECRET_REPLACEMENT,
    RuntimeDlpFinding,
    RuntimeDlpScanResult,
    redact_fail_closed,
    scan_reason_codes,
    scan_runtime,
)

__all__ = [
    "SAFE_SECRET_REPLACEMENT",
    "RuntimeDlpFinding",
    "RuntimeDlpScanResult",
    "redact_fail_closed",
    "scan_reason_codes",
    "scan_runtime",
]
