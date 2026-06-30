from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapter_registry import AdapterRegistry, register_default_adapters
from .contracts import GateResult, IntegratedLearningError, validate_candidate_contract


@dataclass
class UnifiedLearningIntakeGate:
    registry: AdapterRegistry

    @classmethod
    def with_default_adapters(cls, *, enable_chat: bool = False) -> "UnifiedLearningIntakeGate":
        return cls(register_default_adapters(enable_chat=enable_chat))

    def evaluate(self, candidate: dict[str, Any]) -> GateResult:
        try:
            validate_candidate_contract(candidate)
        except IntegratedLearningError as exc:
            return GateResult.drop(str(exc))

        # Top-level invariants are checked by the contract validator. Keep explicit
        # fail-closed guards here so future contract changes cannot silently weaken
        # the runtime gate.
        if candidate.get("policy_decision") != "allow":
            return GateResult.drop("POLICY_NOT_ALLOW")
        if candidate.get("external_send_zero") is not True:
            return GateResult.drop("EXTERNAL_SEND_NOT_ZERO")
        if candidate.get("raw_text_logged") is not False:
            return GateResult.drop("RAW_TEXT_LOGGED")
        if candidate.get("auto_apply_to_runtime") is not False:
            return GateResult.drop("AUTO_APPLY_FORBIDDEN")
        if candidate.get("model_training") is not False or candidate.get("peft_training") is not False:
            return GateResult.drop("TRAINING_FORBIDDEN")
        if "integration_mode" in candidate:
            return GateResult.drop("INTEGRATION_MODE_FORBIDDEN")

        return self.registry.verify(candidate)
