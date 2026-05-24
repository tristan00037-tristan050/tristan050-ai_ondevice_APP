from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .model_registry import registry_from_ip1_status

@dataclass(frozen=True)
class IP2PEPBridgeResult:
    allow: bool
    decision: str
    policy_label: str
    audit_chain_digest: str
    residual_pii: int
    bridge_live_claimed: bool = False

    def as_policy_decision(self) -> dict[str, Any]:
        return {"allow": self.allow, "decision": self.decision, "policy_label": self.policy_label, "audit_chain_digest": self.audit_chain_digest}


def simulate_ip2_pep_contract(policy_label: str, *, allow: bool = True, residual_pii: int = 0) -> IP2PEPBridgeResult:
    # Contract harness: no raw data, only decision metadata.
    return IP2PEPBridgeResult(
        allow=allow and residual_pii == 0,
        decision="allow" if allow and residual_pii == 0 else "blocked",
        policy_label=policy_label,
        audit_chain_digest="0" * 64,
        residual_pii=residual_pii,
        bridge_live_claimed=False,
    )


def build_ip1_model_registry_from_status(status_payload: Mapping[str, Any]):
    forward_verified = bool(status_payload.get("forward_verified"))
    logits_digest = status_payload.get("logits_digest") if forward_verified else None
    return registry_from_ip1_status(forward_verified=forward_verified, logits_digest=logits_digest)
