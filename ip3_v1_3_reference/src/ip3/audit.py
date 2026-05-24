from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Mapping
from .privacy import canonical_digest

@dataclass(frozen=True)
class AuditEvent:
    schema_version: str
    event_type: str
    timestamp_utc: str
    request_digest: str
    decision_digest: str
    prev_hash: str | None
    event_hash: str
    metadata: Mapping[str, Any]


def build_audit_event(event_type: str, request_digest: str, decision: Mapping[str, Any], *, prev_hash: str | None = None, metadata: Mapping[str, Any] | None = None) -> AuditEvent:
    base = {
        "schema_version": "ip3.audit.v1.3.2",
        "event_type": event_type,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request_digest": request_digest,
        "decision_digest": canonical_digest(decision),
        "prev_hash": prev_hash,
        "metadata": dict(metadata or {}),
    }
    event_hash = canonical_digest(base)
    return AuditEvent(event_hash=event_hash, **base)
