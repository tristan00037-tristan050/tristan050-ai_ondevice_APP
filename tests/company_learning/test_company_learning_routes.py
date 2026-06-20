from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.company_learning.job_store import CompanyLearningJobStore
from butler_pc_core.auth.capability_token import CapabilityTokenManager
from butler_pc_core.company_policy.contracts import sha256_text
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore
from butler_pc_core.sidecar.routes import company_learning as route_module


def _app(monkeypatch) -> TestClient:
    monkeypatch.setattr(route_module, "_JOB_STORE", CompanyLearningJobStore())
    monkeypatch.setattr(route_module, "_LEARNING_EVENT_STORE", LearningEventStore())
    monkeypatch.setattr(route_module, "_TOKEN_MANAGER", CapabilityTokenManager())
    app = FastAPI()
    app.include_router(route_module.router)
    client = TestClient(app)
    client.headers.pop("Authorization", None)
    return client


def _headers(monkeypatch) -> dict[str, str]:
    token = "company-learning-token"
    monkeypatch.setattr(route_module._TOKEN_MANAGER, "_token", token)
    return {
        "Authorization": f"Bearer {token}",
        "x-admin-role": "admin",
        "x-admin-id-digest": sha256_text("company-learning-admin"),
        "x-admin-session-digest": sha256_text("company-learning-admin-session"),
        "x-admin-auth-method": "tauri_secure_invoke",
    }


def test_routes_require_capability_token_and_admin_context(tmp_path, monkeypatch):
    client = _app(monkeypatch)

    missing_token = client.get("/v1/company-learning/status", params={"job_id": "clj-missing"})
    assert missing_token.status_code == 401
    assert missing_token.json()["detail"]["fail_class"] == "CAPABILITY_TOKEN_MISSING"

    token_only = _headers(monkeypatch)
    token_only.pop("x-admin-id-digest")
    denied = client.get("/v1/company-learning/status", params={"job_id": "clj-missing"}, headers=token_only)
    assert denied.status_code == 403
    assert denied.json()["detail"]["fail_class"] == "ADMIN_AUTH_REQUIRED"


def test_routes_reject_non_localhost_before_token_check(tmp_path, monkeypatch):
    client = _app(monkeypatch)
    monkeypatch.setattr(route_module, "LOCALHOST_HOSTS", set())

    response = client.get("/v1/company-learning/status", params={"job_id": "clj-missing"})

    assert response.status_code == 403
    body = response.json()
    assert body["detail"]["fail_class"] == "LOCALHOST_ONLY"
    assert body["detail"]["raw_text_logged"] is False
    assert body["detail"]["external_send_zero"] is True


def test_connect_understanding_and_handoff_are_raw_zero(tmp_path, monkeypatch):
    raw_folder_name = "sensitive-client-folder"
    raw_file_name = "client-secret-plan.txt"
    folder = tmp_path / raw_folder_name
    folder.mkdir()
    (folder / raw_file_name).write_text("업무 절차와 승인 흐름을 로컬에서 검토합니다.", encoding="utf-8")

    client = _app(monkeypatch)
    headers = _headers(monkeypatch)

    connected = client.post(
        "/v1/company-learning/folder/connect",
        headers=headers,
        json={"folder_path": str(folder)},
    )
    assert connected.status_code == 200
    body = connected.json()
    job_id = body["job_id"]
    encoded_connect = json.dumps(body, ensure_ascii=False)
    assert raw_folder_name not in encoded_connect
    assert raw_file_name not in encoded_connect
    assert body["raw_text_logged"] is False
    assert body["external_send_zero"] is True

    status = client.get("/v1/company-learning/status", params={"job_id": job_id}, headers=headers)
    assert status.status_code == 200
    sbody = status.json()
    assert sbody["progress"] == 100
    encoded_status = json.dumps(sbody, ensure_ascii=False)
    assert raw_folder_name not in encoded_status
    assert raw_file_name not in encoded_status

    understanding = client.get("/v1/company-learning/understanding", params={"job_id": job_id}, headers=headers)
    assert understanding.status_code == 200
    ubody = understanding.json()
    encoded_understanding = json.dumps(ubody, ensure_ascii=False)
    assert raw_folder_name not in encoded_understanding
    assert raw_file_name not in encoded_understanding
    assert "업무 절차와 승인 흐름" not in encoded_understanding
    assert ubody["claims"]
    assert all(claim["evidence_chips"] for claim in ubody["claims"])

    handoff = client.post(
        "/v1/company-learning/handoff",
        headers=headers,
        json={"job_id": job_id},
    )
    assert handoff.status_code == 200
    hbody = handoff.json()
    assert hbody["status"] == "CANDIDATE"
    assert hbody["verified_for_training"] is False
    assert hbody["approved_text_ref"].startswith("vault://company-learning/")
    encoded_handoff = json.dumps(hbody, ensure_ascii=False)
    assert raw_folder_name not in encoded_handoff
    assert raw_file_name not in encoded_handoff


def test_unsupported_only_folder_fails_closed_without_path_leak(tmp_path, monkeypatch):
    folder = tmp_path / "raw-folder-name"
    folder.mkdir()
    (folder / "secret.bin").write_bytes(b"binary")
    client = _app(monkeypatch)

    response = client.post(
        "/v1/company-learning/folder/connect",
        headers=_headers(monkeypatch),
        json={"folder_path": str(folder)},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["detail"]["fail_class"] == "NO_INDEXABLE_FILES"
    encoded = json.dumps(body, ensure_ascii=False)
    assert "raw-folder-name" not in encoded
    assert "secret.bin" not in encoded
