"""Regression guards for removal of the legacy Helper1 placeholder route."""
from __future__ import annotations

import inspect
import uuid

import pytest

pytest.importorskip("fastapi")
pytestmark = pytest.mark.active_policy


def _client_and_token():
    from fastapi.testclient import TestClient

    import butler_sidecar

    token = butler_sidecar._TOKEN_MANAGER.generate()
    return TestClient(butler_sidecar.app), token


def _payload():
    return {
        "schema_version": "butler.helper1.ask-request.v2",
        "request_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "query": "test",
        "top_k": 5,
        "requested_generation_id": None,
        "effect_intent": "display_only",
    }


def test_asset_absence_is_typed_503():
    client, token = _client_and_token()
    response = client.post(
        "/v1/helpers/1/search",
        json=_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 503
    assert response.json()["kind"] == "REFUSED_ASSET_MISSING"


def test_answer_absence_has_no_stub_or_sources():
    client, token = _client_and_token()
    response = client.post(
        "/v1/helpers/1/ask",
        json=_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    value = response.json()
    assert response.status_code == 503
    assert value["answer"] is None
    assert value["citations"] == []


def test_route_is_thin_and_contains_no_dynamic_sdk_or_developer_paths():
    import butler_pc_core.sidecar.routes.helper1_search as route

    source = inspect.getsource(route)
    forbidden = (
        "sys.path.insert",
        "sys.path.append",
        "import memory_helper",
        "pickle.load",
        "allow_pickle=True",
        "CONTRACT_ONLY_ANSWER",
    )
    assert all(value not in source for value in forbidden)
    assert "get_helper1_service" in source
    assert "anyio.to_thread.run_sync" in source


def test_invalid_payload_does_not_leak_raw_value():
    client, token = _client_and_token()
    value = _payload()
    value["bad"] = "LOCAL_PATH_SENTINEL"
    response = client.post(
        "/v1/helpers/1/ask",
        json=value,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert "LOCAL_PATH_SENTINEL" not in response.text
