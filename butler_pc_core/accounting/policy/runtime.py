from __future__ import annotations

import os
import threading

from .errors import PolicyLoadError
from .loader import PolicyBundleSnapshot, load_policy_bundle


class PolicyRuntime:
    """One-shot policy lifecycle; a process restart is required for replacement."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: PolicyBundleSnapshot | None = None

    def initialize(
        self,
        bundle_dir: str | os.PathLike[str],
        *,
        expected_manifest_sha256: str,
    ) -> PolicyBundleSnapshot:
        with self._lock:
            if self._snapshot is not None:
                raise PolicyLoadError("POLICY_IMMUTABLE", "RELOAD_AFTER_START")
            snapshot = load_policy_bundle(bundle_dir, expected_manifest_sha256=expected_manifest_sha256)
            self._snapshot = snapshot
            return snapshot

    def snapshot(self) -> PolicyBundleSnapshot:
        with self._lock:
            if self._snapshot is None:
                raise PolicyLoadError("POLICY_RUNTIME", "NOT_INITIALIZED")
            return self._snapshot
