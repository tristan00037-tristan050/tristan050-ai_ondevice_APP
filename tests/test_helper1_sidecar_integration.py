from __future__ import annotations

import uuid

import pytest

pytest.importorskip("fastapi")
pytestmark = pytest.mark.active_policy


def _client_and_token():
    from fastapi.testclient import TestClient

    import butler_sidecar

    token = butler_sidecar._TOKEN_MANAGER.generate()
    return TestClient(butler_sidecar.app), token, butler_sidecar


def _payload(**overrides):
    value = {
        "schema_version": "butler.helper1.ask-request.v2",
        "request_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "query": "지난 분기 매출 보고",
        "top_k": 5,
        "requested_generation_id": None,
        "effect_intent": "display_only",
    }
    value.update(overrides)
    return value


def test_helper1_v2_endpoints_registered():
    _, _, module = _client_and_token()
    paths = set(module.app.openapi()["paths"])
    assert "/v1/helpers/1/status" in paths
    assert "/v1/helpers/1/search" in paths
    assert "/v1/helpers/1/ask" in paths


def test_missing_search_assets_refuse_instead_of_http_200_empty_results():
    client, token, _ = _client_and_token()
    response = client.post(
        "/v1/helpers/1/search",
        json=_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    value = response.json()
    assert value["kind"] == "REFUSED_ASSET_MISSING"
    assert value["answer"] is None


def test_missing_answer_assets_refuse_without_placeholder_answer():
    client, token, _ = _client_and_token()
    response = client.post(
        "/v1/helpers/1/ask",
        json=_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    value = response.json()
    assert value["kind"] == "REFUSED_ASSET_MISSING"
    assert value["answer"] is None
    assert value["citations"] == []


def test_helper1_response_contains_no_query_or_path_digest_audit():
    client, token, _ = _client_and_token()
    secret = "UNIQUE_SECRET_QUERY_STRING_12345"
    response = client.post(
        "/v1/helpers/1/ask",
        json=_payload(query=secret),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert secret not in response.text
    assert "query_digest" not in response.text
    assert "model_path" not in response.text


def test_helper1_rejects_non_localhost(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as route

    monkeypatch.setattr(route, "is_localhost_request", lambda request: False)
    client, token, _ = _client_and_token()
    response = client.post(
        "/v1/helpers/1/ask",
        json=_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["fail_class"] == "LOCALHOST_ONLY"


def test_helper1_requires_capability_token():
    from fastapi.testclient import TestClient

    import butler_sidecar

    butler_sidecar._TOKEN_MANAGER.generate()
    response = TestClient(butler_sidecar.app).post(
        "/v1/helpers/1/search", json=_payload()
    )
    assert response.status_code in {401, 403}


def test_request_unknown_field_rejected_without_echo():
    client, token, _ = _client_and_token()
    response = client.post(
        "/v1/helpers/1/ask",
        json=_payload(unexpected="DO_NOT_ECHO_THIS"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert "DO_NOT_ECHO_THIS" not in response.text


def test_box2_box3_routes_not_regressed():
    _, _, module = _client_and_token()
    paths = set(module.app.openapi()["paths"])
    assert "/v1/cards/2/rewrite" in paths
    assert "/v1/cards/3/draft" in paths
