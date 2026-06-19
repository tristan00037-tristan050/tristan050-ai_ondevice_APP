from __future__ import annotations

import pytest

from butler_pc_core.company_policy import admin_auth
from butler_pc_core.company_policy.admin_auth import AdminAuthError, verify_admin_context
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.role_registry import RoleRegistryStore


def _admin(name: str = "registered", role: str = "admin") -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text(name),
        role=role,  # type: ignore[arg-type]
        admin_session_digest=sha256_text(f"{name}-session"),
        auth_method="tauri_secure_invoke",
    )


def test_public_verify_blocks_empty_and_unregistered_admin(tmp_path, monkeypatch):
    store = RoleRegistryStore(root=tmp_path / "registry")
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: store)

    with pytest.raises(AdminAuthError) as empty:
        verify_admin_context(_admin("first"), operation="register_company_policy")
    assert empty.value.fail_class == "ADMIN_ROLE_REGISTRY_EMPTY"

    store.bootstrap_self_admin(_admin("root"))
    with pytest.raises(AdminAuthError) as missing:
        verify_admin_context(_admin("first"), operation="register_company_policy")
    assert missing.value.fail_class == "ADMIN_ROLE_NOT_REGISTERED"


def test_public_verify_allows_registered_admin_and_blocks_registered_manager(tmp_path, monkeypatch):
    store = RoleRegistryStore(root=tmp_path / "registry")
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: store)
    root = _admin("root")
    store.bootstrap_self_admin(root)
    store.upsert_member(actor=root, target_admin_id_digest=sha256_text("manager"), role="manager")

    assert verify_admin_context(root, operation="register_company_policy").admin_id_digest == root.admin_id_digest

    with pytest.raises(AdminAuthError) as mismatch:
        verify_admin_context(_admin("manager"), operation="register_company_policy")
    assert mismatch.value.fail_class == "ADMIN_ROLE_MISMATCH"
