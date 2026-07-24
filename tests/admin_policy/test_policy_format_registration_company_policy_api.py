from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler_pc_core.cards.box3.adapters.company_format_adapter import apply_company_format_runtime
from butler_pc_core.company_policy.admin_auth import AdminAuthError, verify_admin_context
from butler_pc_core.company_policy.audit import (
    GLOBAL_ADMIN_AUDIT_STORE,
    assert_audit_record_digest_only,
    build_admin_audit_record,
)
from butler_pc_core.company_policy.contracts import (
    AccessRule,
    AdminContext,
    ContractValidationError,
    make_company_format,
    make_company_policy,
    sha256_text,
    validate_company_format_dict,
    validate_company_policy_dict,
)
from butler_pc_core.company_policy.policy_gate import PolicyGate, build_policy_task_envelope
from butler_pc_core.company_policy.role_registry import RoleRegistryStore
from butler_pc_core.company_policy.storage import CompanyFormatStore, PolicyLoadError, PolicyStore


ADMIN_DIGEST = sha256_text("admin-001")
SESSION_DIGEST = sha256_text("admin-session-001")
EMPLOYEE_DIGEST = sha256_text("employee-001")
DEPT_DIGEST = sha256_text("dept-finance")
TENANT_DIGEST = sha256_text("tenant-main")


@pytest.fixture(autouse=True)
def _registered_admin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from butler_pc_core.company_policy import admin_auth

    registry = RoleRegistryStore(root=tmp_path / "role-registry")
    registry.bootstrap_self_admin(admin())
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: registry)


def admin(role: str = "admin") -> AdminContext:
    return AdminContext(
        admin_id_digest=ADMIN_DIGEST if role == "admin" else EMPLOYEE_DIGEST,
        role=role,  # type: ignore[arg-type]
        admin_session_digest=SESSION_DIGEST,
        auth_method="tauri_secure_invoke",
    )


def access_rule(*, decision: str = "allow", doc_grade: str = "internal") -> AccessRule:
    return AccessRule(
        dept_digest=DEPT_DIGEST,
        role="employee",
        doc_grade=doc_grade,  # type: ignore[arg-type]
        decision=decision,  # type: ignore[arg-type]
        reason_code="RULE_MATCHED",
    )


def policy(*, decision: str = "allow", masking_verified: bool = False):
    return make_company_policy(
        registered_by_digest=ADMIN_DIGEST,
        masking_engine_verified=masking_verified,
        access_rules=[access_rule(decision=decision)],
    )


def envelope(**overrides):
    base = dict(
        request_id="req-001",
        tenant_digest=TENANT_DIGEST,
        dept_digest=DEPT_DIGEST,
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
    base.update(overrides)
    return build_policy_task_envelope(**base)


def test_01_schema_validation_additional_properties_fail_closed():
    p = policy().to_dict()
    p["unexpected"] = "x"
    with pytest.raises(ContractValidationError):
        validate_company_policy_dict(p)

    f = make_company_format(
        format_id="fmt-001",
        format_kind="report",
        status="ACTIVE",
        template_ref="local-vault://formats/templates/template-001",
        template_digest=sha256_text("template"),
        metadata={"title_digest": sha256_text("title"), "language": "ko", "dept_digest": DEPT_DIGEST},
        registered_by_digest=ADMIN_DIGEST,
    ).to_dict()
    f["extra"] = "x"
    with pytest.raises(ContractValidationError):
        validate_company_format_dict(f)


def test_02_admin_auth_non_admin_rejected_and_capability_token_not_admin():
    with pytest.raises(AdminAuthError):
        verify_admin_context(admin("employee"), operation="register_company_policy")
    with pytest.raises(AdminAuthError):
        verify_admin_context(admin("manager"), operation="register_company_format")


def test_03_bootstrap_fail_closed_box_call_zero():
    calls = {"count": 0}
    gate = PolicyGate.evaluate(envelope(), None)
    if gate.allowed:
        calls["count"] += 1
    assert gate.allowed is False
    assert gate.decision == "block"
    assert gate.block_reason == "POLICY_BOOTSTRAP_REQUIRED"
    assert calls["count"] == 0


def test_04_policy_allow_calls_box_after_gate():
    calls = {"count": 0}
    gate = PolicyGate.evaluate(envelope(), policy())
    if gate.allowed:
        calls["count"] += 1
    assert gate.allowed is True
    assert gate.decision == "allow"
    assert calls["count"] == 1


def test_05_policy_deny_blocks_before_ai_helper_call():
    calls = {"count": 0}
    gate = PolicyGate.evaluate(envelope(), policy(decision="block"))
    if gate.allowed:
        calls["count"] += 1
    assert gate.allowed is False
    assert gate.decision == "block"
    assert gate.block_reason == "RULE_MATCHED"
    assert calls["count"] == 0


def test_06_external_send_confidential_block_and_mask_unverified_not_allow():
    confidential = make_company_policy(
        registered_by_digest=ADMIN_DIGEST,
        access_rules=[access_rule(decision="allow", doc_grade="confidential")],
    )
    ext = PolicyGate.evaluate(envelope(doc_grade="confidential", external_send_requested=True), confidential)
    assert ext.allowed is False
    assert ext.block_reason == "POLICY_EXTERNAL_SEND_BLOCKED"

    mask = PolicyGate.evaluate(envelope(masking_requested=True), policy(masking_verified=False))
    assert mask.allowed is False
    assert mask.decision == "needs_review"
    assert mask.block_reason == "POLICY_MASKING_ENGINE_UNVERIFIED"


def test_07_policy_load_failure_blocks_box_call_zero(tmp_path: Path):
    store = PolicyStore(root=tmp_path / "policy")
    store.index_path.write_text(json.dumps({"active_policy_ref": "local-vault://missing", "policy_digest": sha256_text("bad")}), encoding="utf-8")
    with pytest.raises(PolicyLoadError):
        store.load_active_policy()
    calls = {"count": 0}
    gate = PolicyGate.evaluate(envelope(), None)
    if gate.allowed:
        calls["count"] += 1
    assert gate.block_reason == "POLICY_BOOTSTRAP_REQUIRED"
    assert calls["count"] == 0


def test_08_format_registration_admin_only_encrypted_store_raw_audit_zero(tmp_path: Path):
    GLOBAL_ADMIN_AUDIT_STORE.clear()
    store = CompanyFormatStore(root=tmp_path / "formats")
    with pytest.raises(AdminAuthError):
        store.register_format(
            template_runtime_text="CONFIDENTIAL_TEMPLATE_SENTINEL {draft}",
            format_kind="report",
            title_runtime_text="표준 보고서",
            language="ko",
            dept_digest=DEPT_DIGEST,
            admin=admin("employee"),
        )

    fmt, audit = store.register_format(
        template_runtime_text="CONFIDENTIAL_TEMPLATE_SENTINEL {draft}",
        format_kind="report",
        title_runtime_text="표준 보고서",
        language="ko",
        dept_digest=DEPT_DIGEST,
        admin=admin(),
    )

    persisted = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "formats").rglob("*.json"))
    assert "CONFIDENTIAL_TEMPLATE_SENTINEL" not in persisted
    assert "표준 보고서" not in persisted
    assert fmt.template_digest == sha256_text("CONFIDENTIAL_TEMPLATE_SENTINEL {draft}")
    assert audit["raw_saved_zero"] is True
    assert audit["raw_text_logged"] is False
    assert_audit_record_digest_only(audit)


def test_09_helper3_format_unregistered_needs_review(tmp_path: Path):
    store = CompanyFormatStore(root=tmp_path / "formats")
    result = apply_company_format_runtime(
        draft_text_runtime_only="draft",
        format_id="missing",
        store=store,
    ).to_dict()
    assert result["format_applied"] is False
    assert result["needs_review"] is True
    assert result["fail_class"] == "FORMAT_NOT_REGISTERED"


def test_10_audit_raw_zero_blocks_sensitive_values():
    audit = build_admin_audit_record(
        action="POLICY_DECISION",
        admin_id_digest=ADMIN_DIGEST,
        object_digest=policy().policy_digest,
        reason_code="OK",
    )
    assert_audit_record_digest_only(audit)
    bad = dict(audit)
    bad["email"] = "admin@example.com"
    with pytest.raises(AssertionError):
        assert_audit_record_digest_only(bad)


def test_11_contract_payload_rejects_raw_keys_and_template_text_keys():
    p = policy().to_dict()
    p["raw_template"] = "plain text"
    with pytest.raises(ContractValidationError):
        validate_company_policy_dict(p)

    f = make_company_format(
        format_id="fmt-raw",
        format_kind="report",
        status="ACTIVE",
        template_ref="local-vault://formats/templates/template-raw",
        template_digest=sha256_text("template"),
        metadata={"title_digest": sha256_text("title"), "language": "ko", "dept_digest": DEPT_DIGEST},
        registered_by_digest=ADMIN_DIGEST,
    ).to_dict()
    f["metadata"]["template_text"] = "plain text"
    with pytest.raises(ContractValidationError):
        validate_company_format_dict(f)


def test_12_helper3_format_registered_digest_only(tmp_path: Path):
    store = CompanyFormatStore(root=tmp_path / "formats")
    fmt, _ = store.register_format(
        template_runtime_text="양식 원문은 암호화 저장",
        format_kind="report",
        title_runtime_text="보고서",
        language="ko",
        dept_digest=DEPT_DIGEST,
        admin=admin(),
    )
    result = apply_company_format_runtime(
        draft_text_runtime_only="초안 본문(runtime only)",
        format_id=fmt.format_id,
        store=store,
    ).to_dict()
    encoded = json.dumps(result, ensure_ascii=False)
    assert result["format_applied"] is True
    assert result["needs_review"] is False
    assert "양식 원문" not in encoded
    assert "초안 본문" not in encoded
    assert result["template_digest"] == fmt.template_digest
    assert result["format_digest"] == fmt.format_digest
    assert result["formatted_digest"].startswith("sha256:")
    assert result["external_send_zero"] is True
    assert result["raw_saved_zero"] is True
