from __future__ import annotations

import pytest

from butler_pc_core.company_policy import admin_auth
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.role_registry import RoleRegistryStore


def _admin(name: str) -> AdminContext:
    return AdminContext(
        admin_id_digest=sha256_text(name),
        role="admin",
        admin_session_digest=sha256_text(f"{name}-session"),
        auth_method="tauri_secure_invoke",
    )


@pytest.fixture(autouse=True)
def _registered_admins_for_company_fact_tests(tmp_path, monkeypatch):
    store = RoleRegistryStore(root=tmp_path / "role_registry")
    root = _admin("company-fact-route-admin")
    store.bootstrap_self_admin(root)
    for name in (
        "company-fact-admin",
        "company-fact-audit-admin",
        "company-fact-resolver-admin",
    ):
        store.upsert_member(actor=root, target_admin_id_digest=sha256_text(name), role="admin")
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: store)
