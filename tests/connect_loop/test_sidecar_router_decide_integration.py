from __future__ import annotations

import importlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from butler_pc_core.connect_loop.box1_router import canonical_sha256
from butler_pc_core.sidecar.middleware.usage_accumulator import get_store


def _chat_request(text: str, request_id: str = "req-prd-followup-001") -> dict[str, Any]:
    digest = "sha256:" + ("0" * 64)
    return {
        "request_id": request_id,
        "session_id_digest": digest,
        "tenant_id_digest": digest,
        "device_id": "butler-desktop-device",
        "user_role": "employee",
        "department_id_digest": digest,
        "text_ref": "device_local_only",
        "text_digest": canonical_sha256(text),
        "attachments": [],
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "chat_request.v1",
    }


def _client() -> TestClient:
    sidecar = importlib.import_module("butler_sidecar")
    manager = getattr(sidecar, "_TOKEN_MANAGER")
    token_dir = Path(tempfile.gettempdir()) / "butler_sidecar_token_tests"
    token_dir.mkdir(parents=True, exist_ok=True)
    manager.token_path = token_dir / "sidecar_token"
    manager.clear()
    token = manager.generate()
    client = TestClient(sidecar.app)
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def _router_payload(text: str, request_id: str = "req-prd-followup-001") -> dict[str, Any]:
    return {
        "chat_request": _chat_request(text, request_id=request_id),
        "runtime": {"runtime_text": text},
    }


def test_router_decide_requires_capability_token() -> None:
    client = _client()
    client.headers.pop("Authorization", None)

    response = client.post("/v1/router/decide", json=_router_payload("이전 문서 찾아줘 검색"))

    assert response.status_code == 401
    assert response.json()["fail_class"] == "CAPABILITY_TOKEN_MISSING"


def test_router_decide_rejects_fake_capability_token() -> None:
    client = _client()

    response = client.post(
        "/v1/router/decide",
        json=_router_payload("이전 문서 찾아줘 검색"),
        headers={"Authorization": "Bearer fake-token"},
    )

    assert response.status_code == 403
    assert response.json()["fail_class"] == "CAPABILITY_TOKEN_INVALID"


def test_router_decide_valid_memory_search_reuses_box1_router() -> None:
    client = _client()
    text = "이전 문서 찾아줘 검색"

    response = client.post("/v1/router/decide", json=_router_payload(text))

    assert response.status_code == 200
    decision = response.json()
    assert decision["intent_label"] == "memory_search"
    assert decision["target_box_id"] == "helper1"
    assert decision["target_endpoint"] == "POST /v1/helpers/1/search"
    assert decision["policy_precheck"] == "allow"


def test_router_decide_digest_mismatch_fails_closed() -> None:
    client = _client()
    payload = _router_payload("이전 문서 찾아줘 검색")
    payload["runtime"]["runtime_text"] = "다른 런타임 본문"

    response = client.post("/v1/router/decide", json=payload)

    assert response.status_code == 200
    decision = response.json()
    assert decision["intent_label"] == "unknown"
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True
    assert decision["reason_code"] == "TEXT_DIGEST_MISMATCH"


def test_router_decide_server_policy_blocks_non_local_host(monkeypatch) -> None:
    route_module = importlib.import_module("butler_pc_core.sidecar.routes.router_decide")
    monkeypatch.setattr(route_module, "LOCALHOST_HOSTS", set())
    client = _client()

    response = client.post("/v1/router/decide", json=_router_payload("이전 문서 찾아줘 검색"))

    assert response.status_code == 200
    decision = response.json()
    assert decision["policy_precheck"] == "block"
    assert decision["target_endpoint"] == "none"
    assert decision["fallback_required"] is True
    assert decision["reason_code"] == "LOCALHOST_ONLY"

@pytest.mark.active_policy
def test_router_to_helper1_box_usage_log_request_id_e2e() -> None:
    client = _client()
    store = get_store()
    store.clear()
    text = "이전 문서 찾아줘 검색"
    request_id = "req-prd-followup-e2e-helper1"

    router_response = client.post("/v1/router/decide", json=_router_payload(text, request_id=request_id))
    assert router_response.status_code == 200
    decision = router_response.json()
    assert decision["target_endpoint"] == "POST /v1/helpers/1/search"

    box_response = client.post(
        "/v1/helpers/1/search",
        json={"query": text, "top_k": 5},
        headers={
            "Authorization": client.headers["Authorization"],
            "x-request-id": request_id,
            "x-routing-confidence": str(decision["routing_confidence"]),
            "x-learning-candidate": "0",
        },
    )

    assert box_response.status_code == 200
    body = box_response.json()
    assert body["external_send_zero"] is True
    assert body["raw_text_logged"] is False
    assert len(store.records) == 1
    record = store.records[0]
    assert record["request_id"] == request_id
    assert record["intent_label"] == "memory_search"
    assert record["box_id"] == "helper1"
    assert record["endpoint"] == "POST /v1/helpers/1/search"
    serialized = str(record)
    assert text not in serialized
    assert "/Users/" not in serialized


@pytest.mark.active_policy
def test_box2_and_box3_payload_shapes_are_real_endpoint_json() -> None:
    client = _client()

    box2 = client.post(
        "/v1/cards/2/rewrite",
        json={
            "foreign_doc": "외부 문서 예시",
            "our_format": "우리 양식 예시",
            "options": {
                "tone": "company_standard",
                "preserve_numbers": True,
                "redact_sensitive": True,
            },
        },
        headers={
            "Authorization": client.headers["Authorization"],
            "x-request-id": "req-prd-followup-box2",
            "x-routing-confidence": "0.88",
            "x-learning-candidate": "0",
        },
    )
    assert box2.status_code == 200
    assert box2.json()["external_send_zero"] is True
    assert box2.json()["raw_doc_logged"] is False

    box3 = client.post(
        "/v1/cards/3/draft",
        json={
            "input_text": "새 상황 초안 작성",
            "prompt_template": "문서 안 근거만 사용해 초안을 작성하세요.",
            "max_new_tokens": 64,
        },
        headers={
            "Authorization": client.headers["Authorization"],
            "x-request-id": "req-prd-followup-box3",
            "x-routing-confidence": "0.91",
            "x-learning-candidate": "0",
        },
    )
    assert box3.status_code == 200
    assert box3.json()["external_send_zero"] is True
    assert box3.json()["raw_doc_logged"] is False
