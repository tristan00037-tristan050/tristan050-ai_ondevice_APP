from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from butler_pc_core.auth.capability_token import CapabilityTokenManager
from butler_pc_core.home.store import HomeStore
from butler_pc_core.sidecar.routes import home


def headers(*, version: int | None = None, key: str | None = None, actor: str | None = None) -> dict[str, str]:
    result = {
        "X-Request-ID": str(uuid.uuid4()),
        "Idempotency-Key": key or str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    if actor is not None:
        result["X-Actor-ID"] = actor
    if version is not None:
        result["If-Match"] = f'"v{version}"'
    return result


def client(tmp_path: Path, *, authenticated: bool = True) -> TestClient:
    home._STORE = HomeStore(tmp_path / "home.sqlite3")
    app = FastAPI()

    @app.middleware("http")
    async def capability_session(request: Request, call_next):
        if authenticated:
            request.state.capability_actor_id = "local-user"
            request.state.capability_session_digest = "a" * 64
        return await call_next(request)

    app.include_router(home.router)
    return TestClient(app)


def turn_payload(content: str = "원문") -> dict[str, object]:
    return {
        "conversation": {
            "id": "conversation-1", "folder_id": None, "title": "요청",
            "title_is_custom": False, "created_at": "2099-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z",
        },
        "message": {"id": "message-1", "role": "user", "content": content, "timestamp": "2099-01-01T00:00:00Z"},
    }


def test_api_rejects_duplicate_keys_nonfinite_negative_zero_and_oversized_body(tmp_path: Path) -> None:
    api = client(tmp_path)
    duplicate = api.post("/v1/home/folders", content='{"name":"A","name":"B","parent_id":null}', headers=headers())
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"]["code"] == "DUPLICATE_JSON_KEY"
    for invalid in ('{"name":NaN,"parent_id":null}', '{"name":-0,"parent_id":null}'):
        response = api.post("/v1/home/folders", content=invalid, headers=headers())
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_JSON"
    oversized = api.post("/v1/home/folders", content=json.dumps({"name": "a" * (2 * 1024 * 1024)}), headers=headers())
    assert oversized.status_code == 413


def test_client_actor_header_is_ignored_for_audit_identity(tmp_path: Path) -> None:
    api = client(tmp_path)
    response = api.post("/v1/home/folders", json={"name": "A", "parent_id": None}, headers=headers(actor="spoofed-admin"))
    assert response.status_code == 201
    with home.get_home_store()._connect(read_only=True) as db:
        assert db.execute("SELECT actor FROM home_audit ORDER BY created_at DESC LIMIT 1").fetchone()[0] == "local-user"


def test_mutation_requires_server_capability_session(tmp_path: Path) -> None:
    api = client(tmp_path, authenticated=False)
    response = api.post("/v1/home/folders", json={"name": "A", "parent_id": None}, headers=headers())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "CAPABILITY_SESSION_REQUIRED"


def test_api_requires_strong_etag_and_terminal_correlation(tmp_path: Path) -> None:
    api = client(tmp_path)
    accepted = api.post("/v1/home/conversations/conversation-1/turns/user", json=turn_payload(), headers=headers())
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["command_receipt"]["status"] == "COMMITTED"
    assert uuid.UUID(body["turn_id"])
    assert uuid.UUID(body["model_request_id"])
    assert accepted.headers["etag"] == '"v1"'
    assert api.patch("/v1/home/conversations/conversation-1", json={"title": "변경"}, headers=headers()).status_code == 428

    completed = api.post(
        "/v1/home/conversations/conversation-1/turns/assistant",
        json={
            "turn_id": body["turn_id"], "model_request_id": body["model_request_id"],
            "message": {"id": "assistant-1", "role": "butler", "content": "답변", "timestamp": "2099-01-01T00:00:00Z"},
        },
        headers=headers(version=1),
    )
    assert completed.status_code == 200
    assert completed.json()["terminal_count"] == 1
    duplicate_terminal = api.post(
        f'/v1/home/model-requests/{body["model_request_id"]}/terminal',
        json={"conversation_id": "conversation-1", "turn_id": body["turn_id"], "state": "FAILED", "error_code": "LATE_FAILURE"},
        headers=headers(),
    )
    assert duplicate_terminal.status_code == 409
    assert duplicate_terminal.json()["detail"]["code"] == "TERMINAL_ALREADY_COMMITTED"


def test_folder_create_replays_byte_equivalent_response(tmp_path: Path) -> None:
    api = client(tmp_path)
    key = str(uuid.uuid4())
    first = api.post("/v1/home/folders", json={"name": "고객", "parent_id": None}, headers=headers(key=key))
    replay = api.post("/v1/home/folders", json={"name": "고객", "parent_id": None}, headers=headers(key=key))
    assert first.status_code == replay.status_code == 201
    assert first.content == replay.content
    assert first.headers["Idempotency-Replayed"] == "false"
    assert replay.headers["Idempotency-Replayed"] == "true"
    changed = api.post("/v1/home/folders", json={"name": "변경", "parent_id": None}, headers=headers(key=key))
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"


def test_bootstrap_and_runtime_status_never_claim_activation(tmp_path: Path) -> None:
    api = client(tmp_path)
    startup = api.get("/v1/home/bootstrap-status").json()
    assert startup["status"] == "HOME_READY"
    assert startup["mutation_allowed"] is True
    runtime = api.get("/v1/home/runtime-status").json()
    assert runtime["policy"]["status"] == "UNKNOWN"
    assert runtime["measurement"]["status"] == "NOT_MEASURED"
    assert runtime["runtime_activation_allowed"] is False


def test_product_sidecar_registers_and_serves_authenticated_home_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import butler_sidecar

    class BootstrapStore:
        @staticmethod
        def startup_status() -> dict[str, object]:
            return {
                "status": "HOME_READY",
                "read_only": False,
                "mutation_allowed": True,
                "model_execution_allowed": True,
                "existing_conversation_count": 0,
                "support_code": "test-only-digest",
                "checked_at": "2026-07-23T00:00:00Z",
            }

        @staticmethod
        def flush() -> None:
            return None

        @staticmethod
        def close() -> None:
            return None

    home.shutdown_home_store()
    monkeypatch.setattr(home, "_STORE", BootstrapStore())
    manager = CapabilityTokenManager(tmp_path / "ipc" / "sidecar.capability")
    monkeypatch.setattr(butler_sidecar, "_TOKEN_MANAGER", manager)
    token = manager.generate()

    try:
        product = TestClient(butler_sidecar.app)
        response = product.get(
            "/v1/home/bootstrap-status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "HOME_READY"
    finally:
        home.shutdown_home_store()
