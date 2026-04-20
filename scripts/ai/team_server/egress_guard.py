from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from typing import Any, Iterator
import importlib


class EgressBlockedError(RuntimeError):
    pass


class EgressGuard:
    def __init__(self) -> None:
        self._patches: list[tuple[Any, str, Any]] = []
        self._active = False

    @staticmethod
    def _blocked(*args: Any, **kwargs: Any) -> Any:
        raise EgressBlockedError("EGRESS_BLOCKED")

    def _patch_attr(self, module: Any, attr_chain: str) -> None:
        target = module
        parts = attr_chain.split(".")
        for part in parts[:-1]:
            target = getattr(target, part)
        leaf = parts[-1]
        original = getattr(target, leaf)
        self._patches.append((target, leaf, original))
        setattr(target, leaf, self._blocked)

    def activate(self) -> None:
        if self._active:
            return
        for mod_name, attr in [
            ("requests", "sessions.Session.request"),
            ("httpx", "Client.request"),
            ("urllib.request", "urlopen"),
            ("socket", "create_connection"),
            ("socket", "socket"),
            ("websockets", "connect"),
        ]:
            try:
                module = importlib.import_module(mod_name)
                self._patch_attr(module, attr)
            except Exception:
                continue
        self._active = True

    def deactivate(self) -> None:
        while self._patches:
            target, leaf, original = self._patches.pop()
            setattr(target, leaf, original)
        self._active = False

    @contextmanager
    def patch_all(self) -> Iterator[None]:
        self.activate()
        try:
            yield
        finally:
            self.deactivate()


class EgressPolicyGuard:
    ALLOWED_INTERNAL = ["team-server-internal", "central-server-proxy"]

    def check_outbound(self, destination: str) -> bool:
        if destination in self.ALLOWED_INTERNAL:
            return True
        snippet = destination[:16]
        digest = sha256(destination.encode("utf-8")).hexdigest()[:16]
        raise EgressBlockedError(f"POLICY_BLOCK:{snippet}:{digest}")
