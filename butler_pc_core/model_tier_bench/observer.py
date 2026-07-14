"""Passive observation hook for model-tier-B benchmark integration.

The hook is a pure side channel: registering an observer changes nothing about any
product function's return value or control flow — it only forwards digest/count
metadata to the registered callback. With no observer registered the hooks are
no-ops. This is what lets the integration test assert observer-off and observer-on
product responses are byte-identical.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Mapping, Optional

_LOCK = threading.Lock()
_OBSERVER: Optional[Callable[[Mapping[str, Any]], None]] = None
_EMIT_FAILURES: list[dict[str, str]] = []


def set_observer(callback: Callable[[Mapping[str, Any]], None]) -> None:
    """Register a passive observation callback (metadata-only)."""
    global _OBSERVER
    with _LOCK:
        _OBSERVER = callback


def clear_observer() -> None:
    """Remove any registered observer; hooks become inert."""
    global _OBSERVER
    with _LOCK:
        _OBSERVER = None


def observer_active() -> bool:
    with _LOCK:
        return _OBSERVER is not None


def emit_failures() -> list[dict[str, str]]:
    """Safe error sink for observer emit failures (R2-P1-011). Non-empty means the
    measurement for this run is invalid even though the product response was not
    affected — product safety and benchmark validity are kept separate."""
    with _LOCK:
        return list(_EMIT_FAILURES)


def reset_failures() -> None:
    with _LOCK:
        _EMIT_FAILURES.clear()


def observe(event: Mapping[str, Any]) -> None:
    """Forward an observation event to the registered callback, if any.

    R2-P1-011: fully isolated. An observer callback exception NEVER propagates into
    the caller and NEVER crashes the product process; it is recorded (code +
    exception type only, no raw) in the safe error sink so the measurement can be
    marked invalid without altering the authoritative product response. Callers must
    pass digest/count metadata only (no raw text, paths, or user identifiers).
    """
    with _LOCK:
        callback = _OBSERVER
    if callback is None:
        return
    try:
        callback(dict(event))
    except Exception as exc:  # noqa: BLE001 - deliberate: isolate all observer errors
        with _LOCK:
            _EMIT_FAILURES.append({"code": "OBSERVER_EMIT_FAILED", "exception_type": type(exc).__name__})
