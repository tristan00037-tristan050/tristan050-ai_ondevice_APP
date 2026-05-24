from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.sidecar.routes.chat_completions import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_chat_completions_returns_dry_run_for_artifact_sealed():
    client = _client()
    response = client.post(
        "/v1/chat/completions",
        json={
            "model_id": "butler-1.7b-v4-rt-q4_k_m",
            "messages": [{"role": "user", "content": "회의록 정리해줘"}],
            "routing_context": {"evidence_class": "sample"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["ip3_routing"]["routing_state"] == "dry_run"
    assert data["ip3_routing"]["routing_target"] == "blocked"
    assert data["ip3_routing"]["actual_model_call"] is False
    assert data["ip3_routing"]["production_hook_deployed"] is False
    assert data["ip3_routing"]["release_claim_allowed"] is False
    assert data["ip3_routing"]["raw_text_persisted"] is False
    assert len(data["ip3_routing"]["request_digest"]) == 64
    assert "회의록" not in str(data)


def test_chat_completions_keeps_openai_compatible_shape():
    response = _client().post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "작성"}]},
    )
    data = response.json()
    assert {"id", "object", "created", "model", "choices", "usage"}.issubset(data)
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert data["usage"]["total_tokens"] == 0


def test_chat_completions_rejects_non_localhost(monkeypatch):
    from butler_pc_core.sidecar.routes import chat_completions

    monkeypatch.setattr(chat_completions, "is_localhost_request", lambda request: False)
    response = _client().post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["fail_class"] == "LOCALHOST_ONLY"


def test_chat_completions_requires_messages():
    response = _client().post("/v1/chat/completions", json={"messages": []})
    assert response.status_code == 200
    data = response.json()
    assert data["ip3_routing"]["actual_model_call"] is False
