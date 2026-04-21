from __future__ import annotations
import contextlib, hashlib
from typing import Optional

class EgressBlockedError(RuntimeError):
    pass

class EgressGuard:
    def __init__(self):
        self.enabled = False

    @contextlib.contextmanager
    def patch_all(self):
        self.enabled = True
        try:
            yield self
        finally:
            self.enabled = False

    def check_call(self, destination: str):
        if self.enabled:
            safe_dest = hashlib.sha256((destination or "").encode()).hexdigest()[:16]
            raise EgressBlockedError(f"EGRESS_BLOCK:{safe_dest}")

class EgressPolicyGuard:
    ALLOWED_INTERNAL = {"central-server-internal", "model-distribution-proxy"}

    def __init__(self):
        self.block_count = 0

    def check_outbound(self, destination: str) -> None:
        if destination not in self.ALLOWED_INTERNAL:
            self.block_count += 1
            safe_dest = hashlib.sha256((destination or "").encode()).hexdigest()[:16]
            raise EgressBlockedError(f"POLICY_BLOCK:{safe_dest}")
