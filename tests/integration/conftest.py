from __future__ import annotations

import pytest

from butler_pc_core.company_policy import admin_auth
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.role_registry import RoleRegistryStore


# Fixture drift: the box2/box5 read-only company-knowledge tests approve facts as
# the "company-knowledge-box-admin" admin, which requires a bootstrapped
# RoleRegistry (else ADMIN_ROLE_REGISTRY_EMPTY). Seed it autouse, mirroring
# tests/company_fact/conftest.py.
@pytest.fixture(autouse=True)
def _seed_role_registry_for_integration(tmp_path, monkeypatch):
    store = RoleRegistryStore(root=tmp_path / "role_registry")
    root = AdminContext(
        admin_id_digest=sha256_text("company-knowledge-box-admin"),
        role="admin",
        admin_session_digest=sha256_text("company-knowledge-box-session"),
        auth_method="tauri_secure_invoke",
    )
    store.bootstrap_self_admin(root)
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: store)
