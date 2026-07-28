from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


SAFE_INTEGER_MAX = 9_007_199_254_740_991
CAPABILITY_KEYS = (
    "company_rules",
    "company_facts",
    "company_formats",
    "folder_learning",
)
PUBLIC_REASONS = frozenset(
    {
        "AUTHORITY_UNREACHABLE",
        "AUTHORITY_INCOMPLETE",
        "AUTHORITY_CHANGED",
        "GENERATION_UNAVAILABLE",
        "CONTRACT_MISMATCH",
        "INTERNAL_ERROR",
    }
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CapabilityState(str, Enum):
    IN_USE = "IN_USE"
    REGISTERED_ONLY = "REGISTERED_ONLY"
    PREVIEW_ONLY = "PREVIEW_ONLY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AuthorityProbe:
    available: bool
    registered: bool
    consumer_bound: bool
    preview_only: bool
    revision: str
    evidence_digest: str

    def validate(self) -> None:
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
    generation: int
    capabilities: Mapping[str, CapabilityState]

    def to_dict(self) -> dict[str, Any]:
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or not 0 <= self.generation <= SAFE_INTEGER_MAX
        ):
            raise ValueError("GENERATION_INVALID")
        if tuple(sorted(self.capabilities)) != tuple(sorted(CAPABILITY_KEYS)):
            raise ValueError("CAPABILITY_KEYS_INVALID")
        values = {key: self.capabilities[key].value for key in CAPABILITY_KEYS}
        if any(value == CapabilityState.UNKNOWN.value for value in values.values()):
            raise ValueError("CANONICAL_SNAPSHOT_HAS_UNKNOWN")
        return {
            "schema_version": 1,
            "source": "CANONICAL",
            "generation": self.generation,
            "capabilities": values,
        }


class LearningCapabilityError(RuntimeError):
    def __init__(self, reason: str) -> None:
        if reason not in PUBLIC_REASONS:
            reason = "INTERNAL_ERROR"
        super().__init__(reason)
        self.reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": "UNAVAILABLE",
            "reason": self.reason,
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
        return CapabilityState.UNKNOWN
    if probe.preview_only:
        return CapabilityState.PREVIEW_ONLY
    if probe.registered and probe.consumer_bound:
        return CapabilityState.IN_USE
    if probe.registered:
        return CapabilityState.REGISTERED_ONLY
    return CapabilityState.UNKNOWN
