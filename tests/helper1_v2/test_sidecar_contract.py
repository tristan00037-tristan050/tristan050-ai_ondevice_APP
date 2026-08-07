from __future__ import annotations

import uuid

import pytest

pytest.importorskip("fastapi")
pytestmark = pytest.mark.active_policy


def _client():
    from fastapi.testclient import TestClient

    import butler_sidecar

    token = butler_sidecar._TOKEN_MANAGER.generate()
    return TestClient(butler_sidecar.app), {"Authorization": f"Bearer {token}"}


def _payload(**overrides):
    value = {
        "schema_version": "butler.helper1.ask-request.v2",
        "client_request_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "query": "회사 정책",
        "top_k": 5,
        "requested_generation_id": None,
        "effect_intent": "display_only",
    }
    value.update(overrides)
    return value


def _index_payload(**overrides):
    value = {
        "schema_version": "butler.helper1.index-request.v2",
        "client_request_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "requested_generation_id": None,
        "effect_intent": "index_only",
    }
    value.update(overrides)
    return value


def test_missing_native_bootstrap_is_typed_503_not_placeholder_success():
    client, headers = _client()
    response = client.post(
        "/v1/helpers/1/ask",
        json=_payload(),
        headers=headers,
    )
    assert response.status_code == 503
    value = response.json()
    assert value["kind"] == "REFUSED_ASSET_MISSING"
    assert value["answer"] is None
    assert value["citations"] == []
    assert value["reason_code"] == "HELPER1_RUNTIME_NOT_BOOTSTRAPPED"


def test_search_missing_native_bootstrap_is_typed_503():
    client, headers = _client()
    response = client.post(
        "/v1/helpers/1/search",
        json=_payload(),
        headers=headers,
    )
    assert response.status_code == 503
    assert response.json()["kind"] == "REFUSED_ASSET_MISSING"


def test_index_missing_native_bootstrap_is_typed_503_not_success():
    client, headers = _client()
    response = client.post(
        "/v1/helpers/1/index",
        json=_index_payload(),
        headers=headers,
    )
    assert response.status_code == 503
    assert response.json()["kind"] == "REFUSED_ASSET_MISSING"


def test_index_rejects_non_index_effect_before_service():
    client, headers = _client()
    response = client.post(
        "/v1/helpers/1/index",
        json=_index_payload(effect_intent="display_only"),
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["reason_code"] == "REQUEST_INVALID"


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "missing envelope"},
        _payload(top_k=True),
        _payload(unexpected="raw-secret-must-not-echo"),
        _payload(schema_version="butler.helper1.ask-request.v1"),
        _payload(requested_generation_id="not-a-uuid"),
    ],
)
def test_invalid_requests_are_stable_and_do_not_echo_input(payload):
    client, headers = _client()
    response = client.post("/v1/helpers/1/ask", json=payload, headers=headers)
    assert response.status_code == 422
    assert response.json()["reason_code"] == "REQUEST_INVALID"
    assert "raw-secret-must-not-echo" not in response.text


def test_duplicate_json_field_is_rejected_without_echo():
    client, headers = _client()
    payload = _payload()
    body = (
        '{"schema_version":"butler.helper1.ask-request.v2",'
        f'"client_request_id":"{payload["client_request_id"]}",'
        f'"workspace_id":"{payload["workspace_id"]}",'
        '"query":"secret-one","query":"secret-two","top_k":5,'
        '"requested_generation_id":null,"effect_intent":"display_only"}'
    )
    response = client.post(
        "/v1/helpers/1/ask",
        content=body,
        headers={**headers, "content-type": "application/json"},
    )
    assert response.status_code == 422
    assert "secret-one" not in response.text
    assert "secret-two" not in response.text


def test_request_id_replay_is_refused_after_first_acceptance():
    client, headers = _client()
    payload = _payload()
    first = client.post("/v1/helpers/1/ask", json=payload, headers=headers)
    second = client.post("/v1/helpers/1/ask", json=payload, headers=headers)
    assert first.status_code == 503
    assert second.status_code == 403
    assert second.json()["kind"] == "REFUSED_POLICY"
    assert second.json()["reason_code"] == "REQUEST_REPLAYED"


def test_server_request_id_is_distinct_from_client_id():
    client, headers = _client()
    payload = _payload()
    response = client.post("/v1/helpers/1/ask", json=payload, headers=headers)
    assert response.json()["request_id"] != payload["client_request_id"]


def test_non_display_effect_is_refused_without_payload_release():
    client, headers = _client()
    response = client.post(
        "/v1/helpers/1/ask",
        json=_payload(effect_intent="clipboard"),
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["reason_code"] == "EFFECT_INTENT_NOT_AUTHORIZED"
    assert response.json()["answer"] is None


def test_status_exposes_immutable_release_boundary():
    client, headers = _client()
    response = client.get("/v1/helpers/1/status", headers=headers)
    assert response.status_code == 200
    value = response.json()
    assert value["product_release_allowed"] is False
    assert value["runtime_activation_allowed"] is False
    assert value["production_claim_allowed"] is False
    assert value["external_network_allowed"] is False
