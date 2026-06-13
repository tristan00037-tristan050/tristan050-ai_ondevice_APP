from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.company_profile.contracts import make_runtime_profile, sha256_text
from butler_pc_core.company_profile.storage import CompanyProfileStore
from butler_pc_core.sidecar.routes import company_profile as route_module


HOLDER_ALIAS = "주식회사 에이티링크"
COMPANY_ALIAS = "에이티링크"
ACCOUNT_NUMBER = "123-456789-01-029"


def _admin_headers() -> dict[str, str]:
    return {
        "x-admin-role": "admin",
        "x-admin-id-digest": sha256_text("local-admin:company-profile-test"),
        "x-admin-session-digest": sha256_text("local-session:company-profile-test"),
        "x-admin-auth-method": "test_only",
    }


def _assert_plaintext_absent(encoded: str) -> None:
    for forbidden in (HOLDER_ALIAS, COMPANY_ALIAS, ACCOUNT_NUMBER, "12345678901029"):
        assert forbidden not in encoded


def test_company_profile_store_vault_load_and_digest_only_index(tmp_path):
    store = CompanyProfileStore(root=tmp_path / "profile_store")
    runtime = make_runtime_profile(
        own_bank_holder_aliases=[HOLDER_ALIAS],
        own_company_aliases=[COMPANY_ALIAS],
        own_account_numbers=[ACCOUNT_NUMBER],
    )

    entry = store.save_profile(runtime)
    loaded = store.load_active_profile()

    assert loaded is not None
    assert loaded.profile_digest == runtime.profile_digest
    assert loaded.own_bank_holder_aliases == [HOLDER_ALIAS]
    assert entry.status == "ACTIVE"
    assert entry.raw_text_logged is False
    assert entry.external_send_zero is True
    assert entry.profile_digest.startswith("sha256:")
    assert all(value.startswith("sha256:") for value in entry.field_digests["own_bank_holder_aliases"])
    assert all(value.startswith("sha256:") for value in entry.field_digests["own_company_aliases"])
    assert all(value.startswith("sha256:") for value in entry.field_digests["own_account_numbers"])

    index_text = store.index_path.read_text(encoding="utf-8")
    _assert_plaintext_absent(index_text)
    assert "holder_alias_hint" in index_text
    assert "account_hint" in index_text

    vault_text = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "profile_store").rglob("*.json"))
    _assert_plaintext_absent(vault_text)


def test_company_profile_register_and_status_routes_digest_only(tmp_path, monkeypatch):
    store = CompanyProfileStore(root=tmp_path / "route_store")
    monkeypatch.setattr(route_module, "_STORE", store)
    app = FastAPI()
    app.include_router(route_module.router)
    client = TestClient(app)

    empty_status = client.get("/v1/company-profile/status")
    assert empty_status.status_code == 200
    assert empty_status.json()["active"] is False

    payload = {
        "own_bank_holder_aliases": [HOLDER_ALIAS],
        "own_company_aliases": [COMPANY_ALIAS],
        "own_account_numbers": [ACCOUNT_NUMBER],
    }
    missing_admin = client.post(
        "/v1/company-profile/register",
        json=payload,
    )
    assert missing_admin.status_code == 403
    assert missing_admin.json()["detail"]["fail_class"] == "ADMIN_AUTH_REQUIRED"
    assert store.load_active_index() is None

    response = client.post(
        "/v1/company-profile/register",
        json=payload,
        headers=_admin_headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "company_profile.register.response.v1"
    assert body["profile_digest"].startswith("sha256:")
    assert body["raw_text_logged"] is False
    assert body["plaintext_persisted"] is False
    assert body["external_send_zero"] is True
    _assert_plaintext_absent(json.dumps(body, ensure_ascii=False))

    status_response = client.get("/v1/company-profile/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["active"] is True
    assert status["display_hints"]
    _assert_plaintext_absent(json.dumps(status, ensure_ascii=False))


def test_suggest_from_accounting_file_is_runtime_only(tmp_path, monkeypatch):
    store = CompanyProfileStore(root=tmp_path / "suggest_store")
    monkeypatch.setattr(route_module, "_STORE", store)
    app = FastAPI()
    app.include_router(route_module.router)
    client = TestClient(app)

    csv_bytes = ("적요,입금,출금,상대계좌예금주명\n타행이체,10000,," + HOLDER_ALIAS + "\n").encode("utf-8")
    response = client.post(
        "/v1/company-profile/suggest-from-accounting-file",
        files={"file": ("sample.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_count"] == 1
    assert body["suggestions"][0]["value_runtime_text"] == HOLDER_ALIAS
    assert body["persisted"] is False
    assert body["plaintext_persisted"] is False
    assert body["raw_text_logged"] is False
    assert body["external_send_zero"] is True
    assert store.load_active_index() is None


def test_company_profile_routes_registered_in_butler_sidecar():
    from butler_sidecar import app

    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/v1/company-profile/status" in paths
    assert "/v1/company-profile/register" in paths
    assert "/v1/company-profile/suggest-from-accounting-file" in paths
