from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.company_fact.storage import CompanyFactStore
from butler_pc_core.company_policy.contracts import sha256_text
from butler_pc_core.company_fact import routes as route_module


ANSWER_TEXT = "Company approved answer for accounting retention policy."
SOURCE_TEXT = "Company handbook verified by admin."


def _app_with_store(tmp_path, monkeypatch) -> tuple[TestClient, CompanyFactStore]:
    store = CompanyFactStore(root=tmp_path / "company_fact_store")
    monkeypatch.setattr(route_module, "_STORE", store)
    app = FastAPI()
    app.include_router(route_module.router)
    client = TestClient(app)
    client.headers.pop("Authorization", None)
    return client, store


def _token_headers(monkeypatch) -> dict[str, str]:
    token = "company-fact-route-test-token"
    monkeypatch.setattr(route_module._TOKEN_MANAGER, "_token", token)
    return {"Authorization": f"Bearer {token}"}


def _admin_headers() -> dict[str, str]:
    return {
        "x-admin-role": "admin",
        "x-admin-id-digest": sha256_text("company-fact-route-admin"),
        "x-admin-session-digest": sha256_text("company-fact-route-session"),
        "x-admin-auth-method": "test_only",
    }


def _candidate_payload() -> dict[str, object]:
    return {
        "category": "company_rules",
        "question_patterns": ["retention policy", "accounting retention rule"],
        "keywords_required": ["retention"],
        "keywords_any": ["policy", "accounting"],
        "answer_runtime_text": ANSWER_TEXT,
        "source": SOURCE_TEXT,
        "source_doc": "company-policy-v1",
        "verified_at": "2026-06-14",
        "confidence": 0.7,
    }


def _assert_plaintext_absent(value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False)
    assert ANSWER_TEXT not in encoded
    assert SOURCE_TEXT not in encoded


def test_status_requires_token_and_empty_store_is_not_error(tmp_path, monkeypatch):
    client, _store = _app_with_store(tmp_path, monkeypatch)

    missing = client.get("/v1/company-facts/status")
    assert missing.status_code == 401
    assert missing.json()["detail"]["fail_class"] == "CAPABILITY_TOKEN_MISSING"

    ok = client.get("/v1/company-facts/status", headers=_token_headers(monkeypatch))
    assert ok.status_code == 200
    assert ok.json()["active_count"] == 0
    assert ok.json()["candidate_count"] == 0


def test_candidate_submit_is_token_only_but_listing_and_approval_are_admin_only(tmp_path, monkeypatch):
    client, store = _app_with_store(tmp_path, monkeypatch)

    submit = client.post(
        "/v1/company-facts/candidates",
        headers=_token_headers(monkeypatch),
        json=_candidate_payload(),
    )
    assert submit.status_code == 200
    fact_id = submit.json()["fact_id"]
    assert submit.json()["status"] == "CANDIDATE"
    _assert_plaintext_absent(submit.json())
    _assert_plaintext_absent(store.index_path.read_text(encoding="utf-8"))

    listed_without_admin = client.get("/v1/company-facts/candidates")
    assert listed_without_admin.status_code == 403

    listed = client.get("/v1/company-facts/candidates", headers=_admin_headers())
    assert listed.status_code == 200
    assert listed.json()["candidate_count"] == 1
    _assert_plaintext_absent(listed.json())

    detail = client.get(f"/v1/company-facts/candidates/{fact_id}", headers=_admin_headers())
    assert detail.status_code == 200
    assert detail.json()["answer_runtime_text"] == ANSWER_TEXT

    denied = client.post(f"/v1/company-facts/candidates/{fact_id}/approve")
    assert denied.status_code == 403

    approved = client.post(f"/v1/company-facts/candidates/{fact_id}/approve", headers=_admin_headers())
    assert approved.status_code == 200
    assert approved.json()["status"] == "ACTIVE"

    status = client.get("/v1/company-facts/status", headers=_token_headers(monkeypatch))
    assert status.status_code == 200
    assert status.json()["active_count"] == 1


def test_resolve_excludes_candidate_and_serves_active_only(tmp_path, monkeypatch):
    client, _store = _app_with_store(tmp_path, monkeypatch)
    headers = _token_headers(monkeypatch)
    submit = client.post("/v1/company-facts/candidates", headers=headers, json=_candidate_payload())
    fact_id = submit.json()["fact_id"]

    candidate_result = client.post(
        "/v1/company-facts/resolve",
        headers=headers,
        json={"query": "retention policy"},
    )
    assert candidate_result.status_code == 200
    assert candidate_result.json()["source"] != "company"
    assert candidate_result.json()["answer"] != ANSWER_TEXT

    approve = client.post(f"/v1/company-facts/candidates/{fact_id}/approve", headers=_admin_headers())
    assert approve.status_code == 200

    active_result = client.post(
        "/v1/company-facts/resolve",
        headers=headers,
        json={"query": "retention policy"},
    )
    assert active_result.status_code == 200
    assert active_result.json()["source"] == "company"
    assert active_result.json()["answer"] == ANSWER_TEXT
    assert active_result.json()["raw_text_logged"] is False
    assert active_result.json()["external_send_zero"] is True


def test_status_fails_closed_for_corrupted_index(tmp_path, monkeypatch):
    client, store = _app_with_store(tmp_path, monkeypatch)
    store.index_path.write_text(json.dumps({"schema_version": "drifted"}), encoding="utf-8")

    response = client.get("/v1/company-facts/status", headers=_token_headers(monkeypatch))

    assert response.status_code == 503
    assert response.json()["detail"]["fail_class"] == "COMPANY_FACT_LOAD_FAILED"


def test_status_fails_closed_when_active_vault_item_is_missing(tmp_path, monkeypatch):
    client, store = _app_with_store(tmp_path, monkeypatch)
    submit = client.post(
        "/v1/company-facts/candidates",
        headers=_token_headers(monkeypatch),
        json=_candidate_payload(),
    )
    fact_id = submit.json()["fact_id"]
    approve = client.post(f"/v1/company-facts/candidates/{fact_id}/approve", headers=_admin_headers())
    assert approve.status_code == 200
    vault_item = tmp_path / "company_fact_store" / "vault" / "company_facts" / f"{fact_id}.json"
    vault_item.unlink()

    response = client.get("/v1/company-facts/status", headers=_token_headers(monkeypatch))

    assert response.status_code == 503
    assert response.json()["detail"]["fail_class"] == "COMPANY_FACT_LOAD_FAILED"


def test_company_fact_routes_registered_in_sidecar():
    from butler_sidecar import app

    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/v1/company-facts/status" in paths
    assert "/v1/company-facts/resolve" in paths
    assert "/v1/company-facts/candidates" in paths
    assert "/v1/company-facts/candidates/{fact_id}/approve" in paths
