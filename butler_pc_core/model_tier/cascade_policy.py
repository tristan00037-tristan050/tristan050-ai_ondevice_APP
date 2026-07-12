from __future__ import annotations

from .box_policies import classify_cascade_reason
from .contracts import BoxPolicy, CascadePlan, GateResult, stable_digest


REQUIRED_REPAIR_INPUTS = (
    "reference_evidence_runtime_only",
    "original_request_runtime_only",
    "primary_draft_runtime_only",
    "primary_fail_reason_code",
)


def plan_shadow_cascade(
    *,
    box_id: str,
    gate: GateResult,
    policy: BoxPolicy,
    high_eligible: bool,
) -> CascadePlan:
    if box_id != "3" or box_id != policy.box_id:
        raise ValueError("CASCADE_POLICY_SCOPE_MISMATCH")
    gate.validate()
    policy.validate()

    reason = gate.reason_code or "PRIMARY_GATE_PASS"
    classified = classify_cascade_reason(gate.reason_code)
    # A caller may make a decision stricter, never weaker, than the SSOT mapping.
    severity = "hard" if gate.severity == "hard" else classified
    soft_allowed = (
        severity == "soft"
        and reason in policy.cascade_soft_reason_codes
        and reason not in policy.hard_block_reason_codes
    )
    would_escalate = bool(not gate.passed and soft_allowed and high_eligible)
    escalation_allowed = bool(would_escalate and policy.max_escalations == 1)
    required_inputs = REQUIRED_REPAIR_INPUTS if soft_allowed else ()
    unsigned = {
        "schema_version": "butler.cascade_plan.v1",
        "box_id": box_id,
        "would_escalate": would_escalate,
        "escalation_allowed": escalation_allowed,
        "reason_code": reason,
        "required_runtime_inputs": list(required_inputs),
        "max_additional_model_calls": 1,
        "shadow_only": True,
        "actual_model_invocations": 0,
    }
    plan = CascadePlan(
        schema_version="butler.cascade_plan.v1",
        box_id=box_id,
        would_escalate=would_escalate,
        escalation_allowed=escalation_allowed,
        reason_code=reason,
        required_runtime_inputs=required_inputs,
        max_additional_model_calls=1,
        shadow_only=True,
        actual_model_invocations=0,
        plan_digest=stable_digest(unsigned),
    )
    plan.validate()
    return plan
