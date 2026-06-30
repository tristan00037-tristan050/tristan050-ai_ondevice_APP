from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler_pc_core.learning_core.contracts import GateResult, is_sha256


@dataclass(frozen=True)
class ChatContextAdapter:
    target_kind: str = "chat_context"
    enabled: bool = False

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        if not self.enabled:
            return GateResult.drop("CHAT_LEARNING_DISABLED")
        payload = candidate.get("payload")
        if not isinstance(payload, dict):
            return GateResult.drop("CHAT_PAYLOAD_MISSING")
        if payload.get("explicit_business_confirmation") is not True:
            return GateResult.drop("CHAT_BUSINESS_CONFIRMATION_REQUIRED")
        if payload.get("manager_or_admin_approved") is not True:
            return GateResult.drop("CHAT_MANAGER_APPROVAL_REQUIRED")
        if payload.get("shadow_eval_cases", 0) < 100:
            return GateResult.drop("CHAT_SHADOW_EVAL_INSUFFICIENT")
        if payload.get("pii_zero") is not True or payload.get("false_learning_zero") is not True:
            return GateResult.drop("CHAT_SHADOW_EVAL_FAILED")
        if not is_sha256(payload.get("context_digest")):
            return GateResult.drop("CHAT_CONTEXT_DIGEST_INVALID")
        return GateResult.accept(candidate)
