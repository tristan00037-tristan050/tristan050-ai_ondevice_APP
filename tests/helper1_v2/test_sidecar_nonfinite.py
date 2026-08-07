from __future__ import annotations

import uuid

import pytest

pytest.importorskip("fastapi")
pytestmark = pytest.mark.active_policy


def test_nonfinite_json_number_is_rejected_fail_closed():
    from fastapi.testclient import TestClient

    import butler_sidecar

    token = butler_sidecar._TOKEN_MANAGER.generate()
    client = TestClient(butler_sidecar.app)
    body = (
        '{"schema_version":"butler.helper1.ask-request.v2",'
        f'"client_request_id":"{uuid.uuid4()}",'
        f'"workspace_id":"{uuid.uuid4()}",'
        '"query":"x","top_k":NaN,"requested_generation_id":null,'
        '"effect_intent":"display_only"}'
    )
    response = client.post(
        "/v1/helpers/1/ask",
        content=body,
        headers={
            "Authorization": f"Bearer {token}",
            "content-type": "application/json",
        },
    )
    assert response.status_code == 422
    assert response.json()["reason_code"] == "REQUEST_INVALID"
