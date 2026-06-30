from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.learning_core.contracts import GateResult, is_sha256


@dataclass(frozen=True)
class ApprovedFactAdapter:
    target_kind: str = "approved_fact"

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            return GateResult.drop("FACT_PAYLOAD_MISSING")
        if payload.get("fact_status") not in {"ACTIVE", "APPROVED"}:
            return GateResult.drop("FACT_NOT_ACTIVE_APPROVED")
        if payload.get("known_bad") is True or payload.get("deprecated") is True or payload.get("superseded") is True:
            return GateResult.drop("FACT_KNOWN_BAD_OR_DEPRECATED")
        if not is_sha256(payload.get("fact_digest")):
            return GateResult.drop("FACT_DIGEST_INVALID")
        return GateResult.accept(candidate)
