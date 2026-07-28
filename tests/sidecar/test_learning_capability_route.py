from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

# The token manager resolves its persistent path at sidecar import time.
os.environ["BUTLER_APP_DATA_DIR"] = tempfile.mkdtemp(
    prefix="butler-fs90-route-",
    dir="/private/tmp",
)

import butler_sidecar
from butler_pc_core.learning_capability.contracts import (
    CapabilityState,
    LearningCapabilityError,
    LearningCapabilitySnapshot,
)
from butler_pc_core.sidecar.routes.learning_capability import (
    get_learning_capability_service,
)


pytestmark = pytest.mark.no_sidecar_token


@dataclass
class _SuccessService:
    def snapshot(self) -> LearningCapabilitySnapshot:
        return LearningCapabilitySnapshot(
            generation=42,
            capabilities={
                "company_rules": CapabilityState.IN_USE,
                "company_facts": CapabilityState.IN_USE,
                "company_formats": CapabilityState.REGISTERED_ONLY,
                "folder_learning": CapabilityState.PREVIEW_ONLY,
            },
        )


@dataclass
class _UnavailableService:
    def snapshot(self) -> LearningCapabilitySnapshot:
        raise LearningCapabilityError("AUTHORITY_INCOMPLETE")


def _request_headers() -> dict[str, str]:
    token = butler_sidecar._TOKEN_MANAGER.token
    assert token
    return {
        "Authorization": f"Bearer {token}",
        "Host": "testserver",
        "Origin": "tauri://localhost",
    }


def _override(service) -> None:
    butler_sidecar.app.dependency_overrides[
        get_learning_capability_service
    ] = lambda: service


def test_learning_capability_route_exists_once_in_app_route_graph():
    def expanded_routes(routes):
        for route in routes:
            original = getattr(route, "original_router", None)
            if original is not None:
                yield from expanded_routes(original.routes)
            else:
                yield route

    matches = [
        route
        for route in expanded_routes(butler_sidecar.app.routes)
        if getattr(route, "path", None) == "/api/capabilities/learning"
        and "GET" in getattr(route, "methods", set())
    ]
    assert len(matches) == 1


def test_success_wire_contract_matches_existing_frontend_parser():
    _override(_SuccessService())
    try:
        with TestClient(butler_sidecar.app) as client:
            response = client.get(
                "/api/capabilities/learning",
                headers=_request_headers(),
            )
        assert response.status_code == 200
        assert response.json() == {
            "schema_version": 1,
            "source": "CANONICAL",
            "generation": 42,
            "capabilities": {
                "company_rules": "IN_USE",
                "company_facts": "IN_USE",
                "company_formats": "REGISTERED_ONLY",
                "folder_learning": "PREVIEW_ONLY",
            },
        }
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
    finally:
        butler_sidecar.app.dependency_overrides.clear()


def test_one_incomplete_authority_returns_503_without_partial_200():
    _override(_UnavailableService())
    try:
        with TestClient(butler_sidecar.app) as client:
            response = client.get(
                "/api/capabilities/learning",
                headers=_request_headers(),
            )
        assert response.status_code == 503
        assert response.json() == {
            "schema_version": 1,
            "source": "UNAVAILABLE",
            "reason": "AUTHORITY_INCOMPLETE",
        }
        assert "capabilities" not in response.json()
    finally:
        butler_sidecar.app.dependency_overrides.clear()


def test_missing_capability_token_is_rejected_before_authority_read():
    called = 0

    def forbidden_factory():
        nonlocal called
        called += 1
        return _SuccessService()

    butler_sidecar.app.dependency_overrides[
        get_learning_capability_service
    ] = forbidden_factory
    try:
        with TestClient(butler_sidecar.app) as client:
            response = client.get(
                "/api/capabilities/learning",
                headers={"Host": "testserver", "Origin": "tauri://localhost"},
            )
        assert response.status_code == 401
        assert called == 0
    finally:
        butler_sidecar.app.dependency_overrides.clear()


def test_invalid_token_host_and_origin_are_rejected():
    _override(_SuccessService())
    try:
        with TestClient(butler_sidecar.app) as client:
            bad_token = client.get(
                "/api/capabilities/learning",
                headers={
                    "Authorization": "Bearer invalid",
                    "Host": "testserver",
                    "Origin": "tauri://localhost",
                },
            )
            bad_host = client.get(
                "/api/capabilities/learning",
                headers={
                    **_request_headers(),
                    "Host": "example.invalid",
                },
            )
            bad_origin = client.get(
                "/api/capabilities/learning",
                headers={
                    **_request_headers(),
                    "Origin": "https://example.invalid",
                },
            )
        assert bad_token.status_code == 403
        assert bad_host.status_code == 400
        assert bad_origin.status_code == 403
    finally:
        butler_sidecar.app.dependency_overrides.clear()
