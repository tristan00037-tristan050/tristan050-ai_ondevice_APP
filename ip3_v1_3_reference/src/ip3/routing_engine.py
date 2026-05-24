from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Mapping, Optional

from .device_classifier import classify_device
from .model_registry import ModelStatus, default_model_registry
from .policy_matrix import allowed_targets, pep_decision_allows
from .user_context import UserContext

@dataclass(frozen=True)
class RoutingDecision:
    routing_state: str
    target: str
    device_class: str
    trust_level: str
    reason: str
    request_digest: str
    model_executable: bool
    policy_allowed: bool
    scores: Mapping[str, float]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RoutingEngine:
    def __init__(self, model_registry: Mapping[str, ModelStatus] | None = None, *, external_api_enabled: bool = False):
        self.model_registry = dict(model_registry or default_model_registry())
        self.external_api_enabled = external_api_enabled

    def decide(self, *, telemetry: Mapping[str, Any], context: UserContext, ip2_policy_decision: Mapping[str, Any]) -> RoutingDecision:
        if not pep_decision_allows(ip2_policy_decision):
            dc = classify_device(telemetry)
            return RoutingDecision(
                routing_state="blocked", target="blocked", device_class=dc.device_class, trust_level=dc.trust_level,
                reason="ip2_policy_denied", request_digest=context.request_digest, model_executable=False, policy_allowed=False,
                scores=context.scores(),
            )

        dc = classify_device(telemetry)
        candidates = allowed_targets(context.data_sensitivity, dc.device_class, external_api_enabled=self.external_api_enabled)
        if "blocked" in candidates and len(candidates) == 1:
            return RoutingDecision("blocked", "blocked", dc.device_class, dc.trust_level, "policy_matrix_blocked", context.request_digest, False, True, context.scores())

        complexity = context.complexity_score()
        selected = "blocked"
        reason = "no_executable_model"
        model_executable = False

        for target in candidates:
            status = self.model_registry.get(target)
            if target == "central_server" and status and status.runtime_live:
                if context.data_sensitivity == "Restricted":
                    continue
                selected, reason, model_executable = target, "central_server_runtime_live", True
                break
            if target == "external_api" and self.external_api_enabled and context.data_sensitivity == "Public" and status and status.runtime_live:
                selected, reason, model_executable = target, "external_api_public_only", True
                break
            if status and status.routing_executable:
                selected, reason, model_executable = target, "local_model_forward_verified", True
                break

        if selected == "blocked":
            return RoutingDecision("failed_closed", "blocked", dc.device_class, dc.trust_level, reason, context.request_digest, False, True, context.scores())
        return RoutingDecision("routed", selected, dc.device_class, dc.trust_level, reason, context.request_digest, model_executable, True, context.scores())
