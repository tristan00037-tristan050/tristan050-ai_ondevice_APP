from __future__ import annotations

import socket
import urllib.request

from fastapi.testclient import TestClient
import pytest

import butler_sidecar
from butler_pc_core.observability.egress_monitor_real import (
    RUNTIME_REAL_MEASUREMENT,
)


def test_egress_endpoint_uses_process_runtime_monitor_and_restores_hooks() -> None:
    original_connect = socket.socket.connect
    with TestClient(butler_sidecar.app) as client:
        token = butler_sidecar._TOKEN_MANAGER.token
        assert token
        assert butler_sidecar._EGRESS_MONITOR is not None
        response = client.get(
            "/api/egress/report",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert socket.socket.connect is original_connect
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "egress_report.v2"
    assert payload["measurement"] == RUNTIME_REAL_MEASUREMENT
    assert payload["verdict"] == "PASS"
    assert "socket" in payload["patched_targets"]
    assert "STATIC_BETA" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_egress_endpoint_reflects_a_blocked_external_attempt() -> None:
    with TestClient(butler_sidecar.app) as client:
        with pytest.raises(PermissionError):
            urllib.request.urlopen("https://runtime-egress.invalid")
        response = client.get(
            "/api/egress/report",
            headers={
                "Authorization": f"Bearer {butler_sidecar._TOKEN_MANAGER.token}",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["measurement"] == RUNTIME_REAL_MEASUREMENT
    assert payload["verdict"] == "FAIL"
    assert payload["external_calls_count"] == 1
    assert payload["external_calls_blocked"] == 1
    assert payload["violations"][0]["kind"] == "urllib"
    assert "runtime-egress.invalid" not in response.text


def test_egress_endpoint_marks_static_beta_when_runtime_monitor_is_absent() -> None:
    with TestClient(butler_sidecar.app) as client:
        token = butler_sidecar._TOKEN_MANAGER.token
        butler_sidecar._stop_egress_monitor()
        response = client.get(
            "/api/egress/report",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "EGRESS_MEASUREMENT_UNAVAILABLE",
        "measurement": "STATIC_BETA",
    }
    assert response.headers["cache-control"] == "no-store"


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
