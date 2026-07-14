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


def observe(event: Mapping[str, Any]) -> None:
    """Forward an observation event to the registered callback, if any.

    Never raises into and never alters the caller: a snapshot of the observer is
    taken under lock and invoked outside the caller's return path. Callers must pass
    digest/count metadata only (no raw text, paths, or user identifiers).
    """
    with _LOCK:
        callback = _OBSERVER
    if callback is not None:
        callback(dict(event))
