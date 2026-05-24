from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable, Mapping

from .audit import build_audit_event
from .bridges import simulate_ip2_pep_contract
from .routing_engine import RoutingEngine
from .user_context import UserContext

class ButlerAppSourceRoutingHook:
    """Digest-only routing hook harness.

    This hook receives already-classified metadata. It never accepts or stores raw prompt/user text.
    """

    def __init__(self, engine: RoutingEngine):
        self.engine = engine
        self.prev_hash: str | None = None

    def handle_event(self, event: Mapping[str, Any], telemetry: Mapping[str, Any]) -> dict[str, Any]:
        context = UserContext.from_metadata(
            task_type=str(event["task_type"]),
            urgency=str(event["urgency"]),
            accuracy_requirement=str(event["accuracy_requirement"]),
            data_sensitivity=str(event["data_sensitivity"]),
            request_fingerprint_seed=str(event["request_seed"]),
        )
        ip2 = simulate_ip2_pep_contract(str(event["data_sensitivity"]), allow=bool(event.get("ip2_allow", True)), residual_pii=int(event.get("residual_pii", 0)))
        decision = self.engine.decide(telemetry=telemetry, context=context, ip2_policy_decision=ip2.as_policy_decision())
        audit = build_audit_event("routing_decision", context.request_digest, decision.as_dict(), prev_hash=self.prev_hash, metadata={"policy_label": event["data_sensitivity"]})
        self.prev_hash = audit.event_hash
        return {"decision": decision.as_dict(), "audit": asdict(audit), "ip2_bridge_live_claimed": ip2.bridge_live_claimed}
