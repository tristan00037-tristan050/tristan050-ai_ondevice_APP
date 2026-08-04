"""Per-run append-only Helper1 product trace with hash chaining."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from .contracts import canonical_json, require_digest, require_uuid, sha256_bytes


class TraceError(RuntimeError):
    pass


PRODUCT_SEQUENCE = (
    "STRICT_REQUEST_DECODED",
    "AUTHORIZATION_RESOLVED",
    "RUN_NONCE_CREATED",
    "TRUST_POLICY_LOADED",
    "MODEL_CLOSURE_VERIFIED",
    "INDEX_MANIFEST_VERIFIED",
    "RETRIEVAL_COMPLETED",
    "CURRENT_CHUNK_BYTES_VERIFIED",
    "GROUNDING_AND_INJECTION_PASSED",
    "GENERATION_BUFFERED",
    "CLAIMS_VERIFIED",
    "DLP_PASSED",
    "EFFECT_AUTHORIZED",
    "OS_EGRESS_VERIFIED",
    "TERMINAL_COMMITTED",
)


@dataclass(frozen=True, slots=True)
class TraceEvent:
    sequence: int
    name: str
    monotonic_ns: int
    previous_digest: str
    metadata_digest: str
    event_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "name": self.name,
            "monotonic_ns": self.monotonic_ns,
            "previous_digest": self.previous_digest,
            "metadata_digest": self.metadata_digest,
            "event_digest": self.event_digest,
        }


@dataclass
class RunTrace:
    request_id: str
    workspace_id: str
    generation_id: str
    session_digest: str
    action: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _events: list[TraceEvent] = field(default_factory=list, init=False, repr=False)
    _terminal: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        require_uuid(self.run_id, "TRACE_RUN_ID_INVALID")
        require_uuid(self.request_id, "TRACE_REQUEST_ID_INVALID")
        require_uuid(self.workspace_id, "TRACE_WORKSPACE_ID_INVALID")
        require_uuid(self.generation_id, "TRACE_GENERATION_ID_INVALID")
        require_digest(self.session_digest, "TRACE_SESSION_INVALID")
        if self.action not in {"ask", "search", "index"}:
            raise TraceError("TRACE_ACTION_INVALID")

    @property
    def root(self) -> str:
        with self._lock:
            return self._events[-1].event_digest if self._events else "0" * 64

    @property
    def terminal_count(self) -> int:
        with self._lock:
            return int(self._terminal)

    def append(self, name: str, metadata: Mapping[str, Any]) -> TraceEvent:
        if type(metadata) is not dict:
            raise TraceError("TRACE_METADATA_INVALID")
        try:
            metadata_digest = sha256_bytes(canonical_json(metadata))
        except (TypeError, ValueError) as exc:
            raise TraceError("TRACE_METADATA_INVALID") from exc
        with self._lock:
            if self._terminal:
                raise TraceError("TRACE_AFTER_TERMINAL")
            expected = PRODUCT_SEQUENCE[len(self._events)] if len(self._events) < len(PRODUCT_SEQUENCE) else None
            if name != expected:
                raise TraceError("TRACE_ORDER_INVALID")
            previous = self._events[-1].event_digest if self._events else "0" * 64
            monotonic_ns = time.monotonic_ns()
            event_value = {
                "schema_version": "butler.helper1.trace-event.v1",
                "run_id": self.run_id,
                "request_id": self.request_id,
                "workspace_id": self.workspace_id,
                "generation_id": self.generation_id,
                "session_digest": self.session_digest,
                "action": self.action,
                "sequence": len(self._events),
                "name": name,
                "monotonic_ns": monotonic_ns,
                "previous_digest": previous,
                "metadata_digest": metadata_digest,
            }
            event = TraceEvent(
                sequence=len(self._events),
                name=name,
                monotonic_ns=monotonic_ns,
                previous_digest=previous,
                metadata_digest=metadata_digest,
                event_digest=sha256_bytes(canonical_json(event_value)),
            )
            self._events.append(event)
            if name == "TERMINAL_COMMITTED":
                self._terminal = True
            return event

    def terminal(self, terminal_kind: str) -> TraceEvent:
        """Fail-closed traces may terminate early; skipped stages are explicit."""
        with self._lock:
            missing = PRODUCT_SEQUENCE[len(self._events) : -1]
        for name in missing:
            self.append(name, {"status": "SKIPPED_FAIL_CLOSED"})
        return self.append("TERMINAL_COMMITTED", {"kind": terminal_kind})

    def verify_complete(self) -> None:
        with self._lock:
            if tuple(event.name for event in self._events) != PRODUCT_SEQUENCE:
                raise TraceError("TRACE_INCOMPLETE")
            if not self._terminal:
                raise TraceError("TRACE_TERMINAL_MISSING")
            previous = "0" * 64
            for event in self._events:
                require_digest(event.event_digest, "TRACE_EVENT_DIGEST_INVALID")
                if event.previous_digest != previous:
                    raise TraceError("TRACE_CHAIN_INVALID")
                previous = event.event_digest
