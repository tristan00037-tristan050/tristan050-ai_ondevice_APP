from __future__ import annotations

import pytest

from butler_pc_core.company_policy import admin_auth
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.role_registry import RoleRegistryStore


def admin_context(name: str = "company-learning-admin") -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text(name),
        role="admin",
        admin_session_digest=sha256_text(f"{name}-session"),
        auth_method="tauri_secure_invoke",
    )


@pytest.fixture(autouse=True)
def _registered_company_learning_admin(tmp_path, monkeypatch):
    store = RoleRegistryStore(root=tmp_path / "role_registry")
    root = admin_context("company-learning-root")
    store.bootstrap_self_admin(root)
    store.upsert_member(
        actor=root,
        target_admin_id_digest=sha256_text("company-learning-admin"),
        role="admin",
    )
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: store)
