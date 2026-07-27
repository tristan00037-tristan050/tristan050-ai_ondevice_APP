from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.company_fact import routes as route_module
from butler_pc_core.company_policy import admin_auth
from butler_pc_core.company_fact.storage import CompanyFactStore
from butler_pc_core.company_policy.admin_auth import (
    AdminAuthError,
    ZERO_DIGEST,
    _verify_admin_context_base,
    admin_error_payload,
    verify_admin_context,
)
from butler_pc_core.company_policy.contracts import AdminContext, sha256_text
from butler_pc_core.company_policy.role_registry import RoleRegistryStore


def _admin_context(
    *,
    admin_id_digest: str | None = None,
    admin_session_digest: str | None = None,
    role: str = "admin",
    auth_method: str = "tauri_secure_invoke",
) -> AdminContext:
    return AdminContext(
        admin_id_digest=admin_id_digest or sha256_text("admin-gate-hardening-admin"),
        role=role,  # type: ignore[arg-type]
        admin_session_digest=admin_session_digest or sha256_text("admin-gate-hardening-session"),
        auth_method=auth_method,  # type: ignore[arg-type]
    )


def _assert_error_is_raw_zero(exc: AdminAuthError) -> None:
    payload = admin_error_payload(exc)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert ZERO_DIGEST not in encoded
    assert "x-admin" not in encoded.lower()
    assert "Authorization" not in encoded
    assert "Bearer" not in encoded
    assert "company-fact-route-session" not in encoded
    assert set(payload) == {"fail_class", "message"}


def _seed_role_registry(tmp_path, monkeypatch, *names: str) -> RoleRegistryStore:
    store = RoleRegistryStore(root=tmp_path / "role_registry")
    root_name = names[0] if names else "company-fact-route-admin"
    root = _admin_context(admin_id_digest=sha256_text(root_name))
    store.bootstrap_self_admin(root)
    for name in names[1:]:
        store.upsert_member(actor=root, target_admin_id_digest=sha256_text(name), role="admin")
    monkeypatch.setattr(admin_auth, "get_default_role_registry_store", lambda: store)
    return store


@pytest.mark.parametrize("field", ["admin_id_digest", "admin_session_digest"])
def test_verify_admin_context_rejects_placeholder_zero_digest(field: str):
    kwargs = {field: ZERO_DIGEST}
    with pytest.raises(AdminAuthError) as raised:
        _verify_admin_context_base(_admin_context(**kwargs), operation="approve_company_fact")

    assert raised.value.fail_class == "ADMIN_DIGEST_PLACEHOLDER"
    _assert_error_is_raw_zero(raised.value)


def test_verify_admin_context_rejects_test_only_without_explicit_test_boundary():
    with pytest.raises(AdminAuthError) as raised:
        _verify_admin_context_base(_admin_context(auth_method="test_only"), operation="approve_company_fact")

    assert raised.value.fail_class == "ADMIN_AUTH_METHOD_NOT_ALLOWED"
    _assert_error_is_raw_zero(raised.value)


def test_verify_admin_context_allows_test_only_with_explicit_test_boundary():
    verified = _verify_admin_context_base(
        _admin_context(auth_method="test_only"),
        operation="approve_company_fact",
        allow_test_auth=True,
    )

    assert verified.auth_method == "test_only"


def test_environment_cannot_enable_test_only_auth(monkeypatch):
    monkeypatch.setenv("BUTLER_TEST_ADMIN_AUTH", "1")

    with pytest.raises(AdminAuthError) as raised:
        _verify_admin_context_base(_admin_context(auth_method="test_only"), operation="approve_company_fact")

    assert raised.value.fail_class == "ADMIN_AUTH_METHOD_NOT_ALLOWED"
    _assert_error_is_raw_zero(raised.value)


def test_verify_admin_context_base_allows_real_admin_methods_and_keeps_regressions():
    verified = _verify_admin_context_base(_admin_context(auth_method="tauri_secure_invoke"), operation="approve_company_fact")
    assert verified.role == "admin"
    verified_keychain = _verify_admin_context_base(_admin_context(auth_method="os_keychain"), operation="approve_company_fact")
    assert verified_keychain.auth_method == "os_keychain"

    with pytest.raises(AdminAuthError) as denied:
        _verify_admin_context_base(_admin_context(role="manager"), operation="approve_company_fact")
    assert denied.value.fail_class == "ADMIN_RBAC_DENIED"

    with pytest.raises(AdminAuthError) as invalid:
        _verify_admin_context_base(_admin_context(admin_id_digest="sha256:bad"), operation="approve_company_fact")
    assert invalid.value.fail_class == "ADMIN_CONTEXT_INVALID"


def test_verify_admin_context_requires_role_registry_registration(tmp_path, monkeypatch):
    store = _seed_role_registry(tmp_path, monkeypatch, "registered-admin")

    verified = verify_admin_context(
        _admin_context(admin_id_digest=sha256_text("registered-admin")),
        operation="approve_company_fact",
    )
    assert verified.admin_id_digest == sha256_text("registered-admin")

    with pytest.raises(AdminAuthError) as missing:
        verify_admin_context(_admin_context(admin_id_digest=sha256_text("unregistered-admin")), operation="approve_company_fact")
    assert missing.value.fail_class == "ADMIN_ROLE_NOT_REGISTERED"


def _app_with_store(tmp_path, monkeypatch) -> tuple[TestClient, CompanyFactStore]:
    store = CompanyFactStore(root=tmp_path / "company_fact_store")
    monkeypatch.setattr(route_module, "_STORE", store)
    app = FastAPI()
    app.include_router(route_module.router)
    return TestClient(app), store


def _token_headers(monkeypatch) -> dict[str, str]:
    token = "company-fact-admin-gate-token"
    monkeypatch.setattr(route_module._TOKEN_MANAGER, "_token", token)
    return {"Authorization": f"Bearer {token}"}


def _candidate_payload() -> dict[str, object]:
    return {
        "category": "company_rules",
        "question_patterns": ["admin gate policy", "admin approval rule"],
        "keywords_required": ["admin"],
        "keywords_any": ["gate", "approval"],
        "answer_runtime_text": "Admin gate hardening candidate answer stays in encrypted vault.",
        "source": "admin-gate-hardening-source",
        "source_doc": "admin-gate-hardening-doc",
        "verified_at": "2026-06-18",
        "confidence": 0.7,
    }


def _admin_headers(*, auth_method: str = "tauri_secure_invoke", zero_id: bool = False) -> dict[str, str]:
    return {
        "x-admin-role": "admin",
        "x-admin-id-digest": ZERO_DIGEST if zero_id else sha256_text("company-fact-route-admin"),
        "x-admin-session-digest": sha256_text("company-fact-route-session"),
        "x-admin-auth-method": auth_method,
    }


def test_company_fact_admin_routes_use_hardened_gate(tmp_path, monkeypatch):
    client, store = _app_with_store(tmp_path, monkeypatch)
    _seed_role_registry(tmp_path, monkeypatch, "company-fact-route-admin")
    submit = client.post("/v1/company-facts/candidates", headers=_token_headers(monkeypatch), json=_candidate_payload())
    assert submit.status_code == 200
    fact_id = submit.json()["fact_id"]

    zero_list = client.get("/v1/company-facts/candidates", headers=_admin_headers(zero_id=True))
    assert zero_list.status_code == 403
    assert zero_list.json()["detail"]["fail_class"] == "ADMIN_DIGEST_PLACEHOLDER"

    blocked_test_only = client.get("/v1/company-facts/candidates", headers=_admin_headers(auth_method="test_only"))
    assert blocked_test_only.status_code == 403
    assert blocked_test_only.json()["detail"]["fail_class"] == "ADMIN_AUTH_METHOD_NOT_ALLOWED"

    listed = client.get("/v1/company-facts/candidates", headers=_admin_headers())
    assert listed.status_code == 200
    assert listed.json()["candidate_count"] == 1

    detail = client.get(f"/v1/company-facts/candidates/{fact_id}", headers=_admin_headers())
    assert detail.status_code == 200

    approved = client.post(f"/v1/company-facts/candidates/{fact_id}/approve", headers=_admin_headers())
    assert approved.status_code == 200
    assert approved.json()["status"] == "ACTIVE"
    active_record = store.load_fact(fact_id)
    active_digest = active_record.fact_digest
    audit_count = len(store.audit_store.records)

    zero_deprecate = client.post(f"/v1/company-facts/{fact_id}/deprecate", headers=_admin_headers(zero_id=True))
    assert zero_deprecate.status_code == 403
    assert zero_deprecate.json()["detail"]["fail_class"] == "ADMIN_DIGEST_PLACEHOLDER"
    assert store.load_fact(fact_id).status == "ACTIVE"
    assert store.load_fact(fact_id).fact_digest == active_digest
    assert len(store.audit_store.records) == audit_count

    blocked_deprecate = client.post(
        f"/v1/company-facts/{fact_id}/deprecate",
        headers=_admin_headers(auth_method="test_only"),
    )
    assert blocked_deprecate.status_code == 403
    assert blocked_deprecate.json()["detail"]["fail_class"] == "ADMIN_AUTH_METHOD_NOT_ALLOWED"
    assert store.load_fact(fact_id).status == "ACTIVE"
    assert store.load_fact(fact_id).fact_digest == active_digest
    assert len(store.audit_store.records) == audit_count

    deprecated = client.post(f"/v1/company-facts/{fact_id}/deprecate", headers=_admin_headers())
    assert deprecated.status_code == 200
    assert deprecated.json()["status"] == "DEPRECATED"

    encoded_error = json.dumps(zero_list.json(), ensure_ascii=False, sort_keys=True)
    assert ZERO_DIGEST not in encoded_error
    assert "company-fact-route-session" not in encoded_error
    assert "Bearer" not in encoded_error
    encoded_deprecate_error = json.dumps(zero_deprecate.json(), ensure_ascii=False, sort_keys=True)
    assert ZERO_DIGEST not in encoded_deprecate_error
    assert "company-fact-route-session" not in encoded_deprecate_error
    assert "Bearer" not in encoded_deprecate_error
