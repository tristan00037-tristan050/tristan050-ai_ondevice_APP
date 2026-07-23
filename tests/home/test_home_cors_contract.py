from __future__ import annotations

from fastapi.testclient import TestClient

import butler_sidecar


def test_browser_can_read_idempotency_replay_transport_metadata() -> None:
    client = TestClient(butler_sidecar.app)
    response = client.get(
        "/health",
        headers={"Origin": "tauri://localhost"},
    )
    assert response.status_code == 200
    exposed = {
        value.strip().lower()
        for value in response.headers["access-control-expose-headers"].split(",")
    }
    assert "idempotency-replayed" in exposed
