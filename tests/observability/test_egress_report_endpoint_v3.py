from __future__ import annotations

from fastapi.testclient import TestClient

import butler_sidecar


def test_unmeasured_egress_endpoint_fails_closed_without_static_zero() -> None:
    with TestClient(butler_sidecar.app) as client:
        token = butler_sidecar._TOKEN_MANAGER.token
        assert token
        response = client.get(
            "/api/egress/report",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 503
    payload = response.json()
    assert payload == {"detail": "EGRESS_MEASUREMENT_UNAVAILABLE"}
    rendered = response.text
    assert '"egress_bytes_total":0' not in rendered
    assert '"verdict":"PASS"' not in rendered


def test_egress_endpoint_rejects_missing_or_untrusted_local_credentials() -> None:
    with TestClient(butler_sidecar.app) as client:
        missing = client.get(
            "/api/egress/report",
            headers={"Authorization": ""},
        )
        untrusted_origin = client.get(
            "/api/egress/report",
            headers={
                "Authorization": f"Bearer {butler_sidecar._TOKEN_MANAGER.token}",
                "Origin": "https://untrusted.example",
            },
        )

    assert missing.status_code == 401
    assert untrusted_origin.status_code == 403
    assert "egress_bytes_total" not in missing.text
    assert "egress_bytes_total" not in untrusted_origin.text
