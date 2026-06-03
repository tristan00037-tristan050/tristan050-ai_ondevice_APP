from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import (
    CompanyPolicy,
    PolicyGateResult,
    PolicyTaskEnvelope,
    ContractValidationError,
    stable_json_digest,
    validate_policy_task_envelope_dict,
)


class PolicyGate:
    """Central fail-closed PolicyGate.

    The gate must run before AI/model/helper/card execution. If the active
    policy is missing, invalid, or non-allow, caller must not call the target box.
    """

    @staticmethod
    def evaluate(envelope: PolicyTaskEnvelope | dict[str, Any], active_policy: CompanyPolicy | None) -> PolicyGateResult:
        if isinstance(envelope, dict):
            validate_policy_task_envelope_dict(envelope)
            env = PolicyTaskEnvelope(**envelope)
        else:
            env = envelope
            env.to_dict()

        if active_policy is None:
            return _result("block", "POLICY_BOOTSTRAP_REQUIRED", None, env)

        try:
            policy_dict = active_policy.to_dict()
        except Exception:
            return _result("block", "POLICY_LOAD_FAILED", None, env)

        if active_policy.status != "ACTIVE":
            return _result("block", "POLICY_NOT_ACTIVE", active_policy.policy_digest, env)

        if env.doc_grade not in active_policy.doc_grades:
            return _result("block", "POLICY_DOC_GRADE_UNKNOWN", active_policy.policy_digest, env)

        if env.external_send_requested:
            external_decision = active_policy.external_send_rules.get(env.doc_grade, "block")
            if external_decision == "block":
                return _result("block", "POLICY_EXTERNAL_SEND_BLOCKED", active_policy.policy_digest, env)
            if external_decision == "needs_review":
                return _result("needs_review", "POLICY_EXTERNAL_SEND_NEEDS_REVIEW", active_policy.policy_digest, env)

        if env.masking_requested and not active_policy.masking_engine_verified:
            # Mask is not allow unless masking engine has verified evidence.
            return _result("needs_review", "POLICY_MASKING_ENGINE_UNVERIFIED", active_policy.policy_digest, env)

        matched = None
        for rule in active_policy.access_rules:
            if (
                rule.dept_digest == env.dept_digest
                and rule.role == env.user_role
                and rule.doc_grade == env.doc_grade
            ):
                matched = rule
                break

        if matched is None:
            return _result(active_policy.default_action, "POLICY_DEFAULT_BLOCK", active_policy.policy_digest, env)

        return _result(matched.decision, matched.reason_code, active_policy.policy_digest, env)


def _result(decision: str, reason: str, policy_digest: str | None, env: PolicyTaskEnvelope) -> PolicyGateResult:
    audit_ref = stable_json_digest({
        "request_id": env.request_id,
        "tenant_digest": env.tenant_digest,
        "dept_digest": env.dept_digest,
        "target_box_id": env.target_box_id,
        "operation": env.operation,
        "doc_grade": env.doc_grade,
        "decision": decision,
        "reason": reason,
        "policy_digest": policy_digest,
    })
    result = PolicyGateResult(
        schema_version="policy_gate_result.v1",
        allowed=decision == "allow",
        decision=decision,  # type: ignore[arg-type]
        block_reason=None if decision == "allow" else reason,
        applied_policy_digest=policy_digest,
        audit_ref=audit_ref,
        external_send_zero=True,
        raw_text_logged=False,
    )
    result.to_dict()
    return result


def build_policy_task_envelope(
    *,
    request_id: str,
    tenant_digest: str,
    dept_digest: str,
    user_role: str,
    target_box_id: str,
    operation: str,
    doc_grade: str,
    external_send_requested: bool = False,
    format_id: str | None = None,
    learning_allowed: bool = False,
    retention_days: int = 30,
    masking_requested: bool = False,
) -> PolicyTaskEnvelope:
    env = PolicyTaskEnvelope(
        schema_version="policy_task_envelope.v1",
        request_id=request_id,
        tenant_digest=tenant_digest,
        dept_digest=dept_digest,
        user_role=user_role,  # type: ignore[arg-type]
        target_box_id=target_box_id,
        operation=operation,
        doc_grade=doc_grade,  # type: ignore[arg-type]
        external_send_requested=external_send_requested,
        format_id=format_id,
        learning_allowed=learning_allowed,
        retention_days=retention_days,
        masking_requested=masking_requested,
    )
    env.to_dict()
    return env
