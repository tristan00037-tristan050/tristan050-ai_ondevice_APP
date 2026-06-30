from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.learning_core.contracts import GateResult, is_sha256


@dataclass(frozen=True)
class PolicyRuleAdapter:
    target_kind: str = "policy_rule"

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            return GateResult.drop("POLICY_PAYLOAD_MISSING")
        if payload.get("policy_status") != "ACTIVE":
            return GateResult.drop("POLICY_NOT_ACTIVE")
        if not is_sha256(payload.get("active_policy_digest")):
            return GateResult.drop("ACTIVE_POLICY_DIGEST_INVALID")
        if payload.get("deny_to_allow_auto") is True:
            return GateResult.drop("DENY_TO_ALLOW_AUTO_FORBIDDEN")
        return GateResult.accept(candidate)
