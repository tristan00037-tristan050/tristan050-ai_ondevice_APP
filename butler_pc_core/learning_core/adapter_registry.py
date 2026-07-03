from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import GateResult, LearningAdapter


@dataclass
class AdapterRegistry:
    _adapters: dict[str, LearningAdapter] = field(default_factory=dict)

    def register(self, adapter: LearningAdapter) -> None:
        if not adapter.target_kind:
            raise ValueError("adapter target_kind required")
        if adapter.target_kind in self._adapters:
            raise ValueError(f"adapter already registered: {adapter.target_kind}")
        self._adapters[adapter.target_kind] = adapter

    def get(self, target_kind: str) -> LearningAdapter | None:
        return self._adapters.get(target_kind)

    def verify(self, candidate: dict[str, Any]) -> GateResult:
        adapter = self.get(str(candidate.get("target_kind", "")))
        if adapter is None:
            return GateResult.drop("ADAPTER_NOT_REGISTERED")
        return adapter.verify(candidate)


def register_default_adapters(*, enable_chat: bool = False, chat_run_mode: str = "production") -> AdapterRegistry:
    # Imports are local to keep learning_core independent from adapter business rules.
    from butler_pc_core.learning_adapters.approved_fact import ApprovedFactAdapter
    from butler_pc_core.learning_adapters.box_rule_patch import BoxRulePatchAdapter
    from butler_pc_core.learning_adapters.chat_context import ChatContextAdapter
    from butler_pc_core.learning_adapters.company_format import CompanyFormatAdapter
    from butler_pc_core.learning_adapters.folder_doc import FolderDocAdapter
    from butler_pc_core.learning_adapters.policy_rule import PolicyRuleAdapter

    registry = AdapterRegistry()
    registry.register(BoxRulePatchAdapter())
    registry.register(PolicyRuleAdapter())
    registry.register(CompanyFormatAdapter())
    registry.register(ApprovedFactAdapter())
    registry.register(FolderDocAdapter())
    registry.register(ChatContextAdapter(enabled=enable_chat, run_mode=chat_run_mode))
    return registry
