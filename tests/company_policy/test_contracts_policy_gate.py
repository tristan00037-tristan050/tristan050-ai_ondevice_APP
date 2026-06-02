from __future__ import annotations

import pytest

from butler_pc_core.company_policy.contracts import (
    AccessRule,
    ContractValidationError,
    make_company_policy,
    sha256_text,
    validate_company_policy_dict,
)
from butler_pc_core.company_policy.policy_gate import PolicyGate, build_policy_task_envelope


ADMIN = sha256_text("admin")
DEPT = sha256_text("dept")
TENANT = sha256_text("tenant")


def policy(decision: str = "allow", masking: bool = False):
    return make_company_policy(
        registered_by_digest=ADMIN,
        masking_engine_verified=masking,
        access_rules=[AccessRule(dept_digest=DEPT, role="employee", doc_grade="internal", decision=decision, reason_code="RULE_MATCHED")],
    )


def env(**overrides):
    data = dict(
        request_id="req-1",
        tenant_digest=TENANT,
        dept_digest=DEPT,
        user_role="employee",
        target_box_id="3",
        operation="draft_write",
        doc_grade="internal",
        external_send_requested=False,
        format_id=None,
        learning_allowed=False,
        retention_days=30,
        masking_requested=False,
    )
    data.update(overrides)
    return build_policy_task_envelope(**data)


def test_schema_validation_additional_properties_fail_closed():
    p = policy().to_dict()
    p["raw_policy"] = "do not allow"
    with pytest.raises(ContractValidationError):
        validate_company_policy_dict(p)


def test_bootstrap_fail_closed_when_policy_missing():
    result = PolicyGate.evaluate(env(), None)
    assert result.allowed is False
    assert result.decision == "block"
    assert result.block_reason == "POLICY_BOOTSTRAP_REQUIRED"


def test_policy_allow():
    result = PolicyGate.evaluate(env(), policy("allow"))
    assert result.allowed is True
    assert result.decision == "allow"
    assert result.external_send_zero is True
    assert result.raw_text_logged is False


def test_policy_deny_blocks_before_box():
    result = PolicyGate.evaluate(env(), policy("block"))
    assert result.allowed is False
    assert result.decision == "block"
    assert result.block_reason == "RULE_MATCHED"


def test_confidential_external_send_blocks():
    p = make_company_policy(
        registered_by_digest=ADMIN,
        access_rules=[AccessRule(dept_digest=DEPT, role="employee", doc_grade="confidential", decision="allow", reason_code="RULE_MATCHED")],
    )
    result = PolicyGate.evaluate(env(doc_grade="confidential", external_send_requested=True), p)
    assert result.allowed is False
    assert result.block_reason == "POLICY_EXTERNAL_SEND_BLOCKED"


def test_masking_unverified_never_allows():
    result = PolicyGate.evaluate(env(masking_requested=True), policy("allow", masking=False))
    assert result.allowed is False
    assert result.decision == "needs_review"
    assert result.block_reason == "POLICY_MASKING_ENGINE_UNVERIFIED"
