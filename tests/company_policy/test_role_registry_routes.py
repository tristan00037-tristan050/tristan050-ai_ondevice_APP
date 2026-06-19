from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.company_policy import admin_auth
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.role_registry import RoleRegistryStore
from butler_pc_core.sidecar.routes import admin_role_registry as route_module


def _admin_headers(name: str = "route-admin", role: str = "admin") -> dict[str, str]:
    return {
        "x-admin-role": role,
        "x-admin-id-digest": sha256_text(name),
        "x-admin-session-digest": sha256_text(f"{name}-session"),
        "x-admin-auth-method": "tauri_secure_invoke",
    }


def _token_headers(monkeypatch) -> dict[str, str]:
    token = "role-registry-route-token"
    monkeypatch.setattr(route_module._TOKEN_MANAGER, "_token", token)
    return {"Authorization": f"Bearer {token}"}


def _app(tmp_path, monkeypatch) -> tuple[TestClient, RoleRegistryStore]:
    store = RoleRegistryStore(root=tmp_path / "registry")
    monkeypatch.setattr(route_module, "_STORE", store)
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: store)
    app = FastAPI()
    app.include_router(route_module.router)
    return TestClient(app), store


def test_status_requires_token_and_prebootstrap_base_admin(tmp_path, monkeypatch):
    client, _store = _app(tmp_path, monkeypatch)

    missing = client.get("/v1/admin/role-registry/status", headers={"Authorization": "", **_admin_headers()})
    assert missing.status_code == 401

    ok = client.get(
        "/v1/admin/role-registry/status",
        headers={**_token_headers(monkeypatch), **_admin_headers()},
    )
    assert ok.status_code == 200
    assert ok.json()["initialized"] is False
    assert ok.json()["active_admin_count"] == 0


def test_bootstrap_once_target_self_only_then_status_requires_registered_admin(tmp_path, monkeypatch):
    client, _store = _app(tmp_path, monkeypatch)
    headers = {**_token_headers(monkeypatch), **_admin_headers()}

    mismatch = client.post(
        "/v1/admin/role-registry/bootstrap",
        headers=headers,
        json={"target_admin_id_digest": sha256_text("other"), "role": "admin"},
    )
    assert mismatch.status_code == 403
    assert mismatch.json()["detail"]["fail_class"] == "ADMIN_ROLE_REGISTRY_TARGET_MISMATCH"

    bootstrap = client.post("/v1/admin/role-registry/bootstrap", headers=headers, json={})
    assert bootstrap.status_code == 200
    assert bootstrap.json()["role"] == "admin"

    again = client.post("/v1/admin/role-registry/bootstrap", headers=headers, json={})
    assert again.status_code == 409

    status = client.get("/v1/admin/role-registry/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["initialized"] is True
    assert status.json()["active_admin_count"] == 1


def test_member_upsert_remove_and_last_admin_block(tmp_path, monkeypatch):
    client, _store = _app(tmp_path, monkeypatch)
    headers = {**_token_headers(monkeypatch), **_admin_headers("root")}
    assert client.post("/v1/admin/role-registry/bootstrap", headers=headers, json={}).status_code == 200

    second = sha256_text("second-admin")
    upsert = client.post(
        "/v1/admin/role-registry/members",
        headers=headers,
        json={"target_admin_id_digest": second, "role": "admin"},
    )
    assert upsert.status_code == 200
    assert upsert.json()["role"] == "admin"

    remove_root = client.delete(f"/v1/admin/role-registry/members/{sha256_text('root')}", headers=headers)
    assert remove_root.status_code == 200

    second_headers = {**_token_headers(monkeypatch), **_admin_headers("second-admin")}
    last = client.delete(f"/v1/admin/role-registry/members/{second}", headers=second_headers)
    assert last.status_code == 409
    assert last.json()["detail"]["fail_class"] == "ADMIN_ROLE_REGISTRY_LAST_ADMIN"


def test_unregistered_admin_cannot_mutate_members(tmp_path, monkeypatch):
    client, _store = _app(tmp_path, monkeypatch)
    root_headers = {**_token_headers(monkeypatch), **_admin_headers("root")}
    assert client.post("/v1/admin/role-registry/bootstrap", headers=root_headers, json={}).status_code == 200

    blocked = client.post(
        "/v1/admin/role-registry/members",
        headers={**_token_headers(monkeypatch), **_admin_headers("intruder")},
        json={"target_admin_id_digest": sha256_text("target"), "role": "manager"},
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["fail_class"] == "ADMIN_ROLE_NOT_REGISTERED"


def test_status_fails_closed_for_corrupted_index(tmp_path, monkeypatch):
    client, store = _app(tmp_path, monkeypatch)
    headers = {**_token_headers(monkeypatch), **_admin_headers()}
    store.index_path.write_text('{"schema_version":"drift"}', encoding="utf-8")

    response = client.get("/v1/admin/role-registry/status", headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"]["fail_class"] == "ADMIN_ROLE_REGISTRY_LOAD_FAILED"


def test_status_fails_closed_when_populated_audit_files_are_missing(tmp_path, monkeypatch):
    client, store = _app(tmp_path, monkeypatch)
    headers = {**_token_headers(monkeypatch), **_admin_headers()}
    assert client.post("/v1/admin/role-registry/bootstrap", headers=headers, json={}).status_code == 200
    (tmp_path / "registry" / "role_registry_audit_log.jsonl").unlink()
    (tmp_path / "registry" / "role_registry_audit_head.json").unlink()

    response = client.get("/v1/admin/role-registry/status", headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"]["fail_class"] == "ADMIN_ROLE_REGISTRY_LOAD_FAILED"
