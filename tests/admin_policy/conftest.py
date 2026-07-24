from __future__ import annotations

import pytest

from butler_pc_core.company_policy import admin_auth
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.role_registry import RoleRegistryStore


# Fixture drift: admin RBAC verification requires a bootstrapped RoleRegistry
# (else verify_admin_context raises ADMIN_ROLE_REGISTRY_EMPTY). The admin_policy
# suite drives register_format/approve as admin-001 but never seeded the
# registry (unlike tests/company_fact/conftest.py). Seed it autouse.
@pytest.fixture(autouse=True)
def _seed_role_registry_for_admin_policy(tmp_path, monkeypatch):
    store = RoleRegistryStore(root=tmp_path / "role_registry")
    root = AdminContext(
        admin_id_digest=sha256_text("admin-001"),
        role="admin",
        admin_session_digest=sha256_text("admin-session-001"),
        auth_method="tauri_secure_invoke",
    )
    store.bootstrap_self_admin(root)
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: store)
