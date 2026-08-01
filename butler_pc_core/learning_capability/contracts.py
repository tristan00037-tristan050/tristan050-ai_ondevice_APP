from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


SAFE_INTEGER_MAX = 9_007_199_254_740_991
CAPABILITY_KEYS = (
    "company_policy",
    "company_fact",
    "company_format",
    "folder_learning",
)
PUBLIC_REASONS = frozenset(
    {
        "AUTHORITY_CHANGED_DURING_SNAPSHOT",
        "AUTHORITY_SET_INVALID",
        "AUTHORITY_PROBE_INVALID",
        "CONSUMER_BINDING_INVALID",
        "TRUST_STATE_INVALID",
        "TRUST_STATE_AUTHENTICITY_UNAVAILABLE",
        "TRUST_STATE_PLATFORM_UNSUPPORTED",
        "SNAPSHOT_GENERATION_UNAVAILABLE",
        "CAPABILITY_SERVICE_UNAVAILABLE",
    }
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CapabilityState(str, Enum):
    IN_USE = "IN_USE"
    REGISTERED = "REGISTERED"
    NOT_REGISTERED = "NOT_REGISTERED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AuthorityProbe:
    key: str
    available: bool
    registered: bool
    consumer_bound: bool
    preview_only: bool
    revision: str
    evidence_digest: str

    def validate(self) -> None:
        if self.key not in CAPABILITY_KEYS:
            raise ValueError("PROBE_KEY_INVALID")
        if not self.available and (
            self.registered or self.consumer_bound or self.preview_only
        ):
            raise ValueError("UNAVAILABLE_PROBE_HAS_POSITIVE_CLAIM")
        if self.consumer_bound and not self.registered:
            raise ValueError("UNREGISTERED_PROBE_HAS_CONSUMER")
        if self.preview_only and self.consumer_bound:
            raise ValueError("PREVIEW_PROBE_HAS_CONSUMER")
        for value in (self.revision, self.evidence_digest):
            if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
                raise ValueError("PROBE_DIGEST_INVALID")


@dataclass(frozen=True)
class LearningCapabilitySnapshot:
    snapshot_revision: str
    generation: int
    capabilities: Mapping[str, CapabilityState]

    def to_dict(self) -> dict[str, Any]:
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or not 1 <= self.generation <= SAFE_INTEGER_MAX
        ):
            raise ValueError("GENERATION_INVALID")
        normalize_object_digest(self.snapshot_revision)
        if tuple(sorted(self.capabilities)) != tuple(sorted(CAPABILITY_KEYS)):
            raise ValueError("CAPABILITY_KEYS_INVALID")
        values = {key: self.capabilities[key].value for key in CAPABILITY_KEYS}
        return {
            "schema_version": 2,
            "source": "CANONICAL",
            "snapshot_revision": self.snapshot_revision,
            "generation": self.generation,
            "capabilities": values,
        }


class LearningCapabilityError(RuntimeError):
    def __init__(self, reason: str) -> None:
        if reason not in PUBLIC_REASONS:
            reason = "CAPABILITY_SERVICE_UNAVAILABLE"
        super().__init__(reason)
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "source": "UNAVAILABLE",
            "error_code": self.reason,
        }


def lower_hex_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_object_digest(value: str) -> str:
    normalized = value.removeprefix("sha256:")
    if _HEX64.fullmatch(normalized) is None:
        raise ValueError("OBJECT_DIGEST_INVALID")
    return normalized


def derive_state(probe: AuthorityProbe) -> CapabilityState:
    probe.validate()
    if not probe.available:
        return CapabilityState.UNAVAILABLE
    if probe.registered and probe.consumer_bound:
        return CapabilityState.IN_USE
    if probe.registered:
        return CapabilityState.REGISTERED
    return CapabilityState.NOT_REGISTERED
