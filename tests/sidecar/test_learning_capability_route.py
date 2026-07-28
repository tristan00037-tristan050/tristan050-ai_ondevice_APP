from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

# The token manager resolves its persistent path at sidecar import time.
os.environ["BUTLER_APP_DATA_DIR"] = tempfile.mkdtemp(
    prefix="butler-fs90-route-",
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


@dataclass
class _SensitiveFailureService:
    def snapshot(self) -> LearningCapabilitySnapshot:
        raise RuntimeError(
            "/Users/private-user/Documents/customer-contract.txt"
        )


@dataclass
class _InvalidSnapshotService:
    snapshot_value: LearningCapabilitySnapshot

    def snapshot(self) -> LearningCapabilitySnapshot:
        return self.snapshot_value


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


def test_product_service_uses_lazy_product_store_getters(monkeypatch):
    from butler_pc_core.company_fact import routes as fact_routes
    from butler_pc_core.sidecar.routes import admin_policy_format
    from butler_pc_core.sidecar.routes import company_learning

    policy_store = object()
    fact_store = object()
    format_store = object()
    learning_store = object()
    monkeypatch.setattr(
        admin_policy_format,
        "get_policy_store",
        lambda: policy_store,
    )
    monkeypatch.setattr(
        admin_policy_format,
        "get_format_store",
        lambda: format_store,
    )
    monkeypatch.setattr(
        fact_routes,
        "get_company_fact_store",
        lambda: fact_store,
    )
    monkeypatch.setattr(
        company_learning,
        "get_learning_event_store",
        lambda: learning_store,
    )

    service = get_learning_capability_service()

    assert [authority.store for authority in service.authorities] == [
        policy_store,
        fact_store,
        format_store,
        learning_store,
    ]


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
        schema = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / "contracts"
                / "learning-capability-response.schema.json"
            ).read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(response.json())
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
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
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["x-content-type-options"] == "nosniff"
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


def test_invalid_capability_token_is_rejected():
    _override(_SuccessService())
    try:
        with TestClient(butler_sidecar.app) as client:
            response = client.get(
                "/api/capabilities/learning",
                headers={
                    "Authorization": "Bearer invalid",
                    "Host": "testserver",
                    "Origin": "tauri://localhost",
                },
            )
        assert response.status_code == 403
    finally:
        butler_sidecar.app.dependency_overrides.clear()


def test_untrusted_host_is_rejected():
    _override(_SuccessService())
    try:
        with TestClient(butler_sidecar.app) as client:
            response = client.get(
                "/api/capabilities/learning",
                headers={
                    **_request_headers(),
                    "Host": "example.invalid",
                },
            )
        assert response.status_code == 400
    finally:
        butler_sidecar.app.dependency_overrides.clear()


def test_untrusted_origin_is_rejected():
    _override(_SuccessService())
    try:
        with TestClient(butler_sidecar.app) as client:
            response = client.get(
                "/api/capabilities/learning",
                headers={
                    **_request_headers(),
                    "Origin": "https://example.invalid",
                },
            )
        assert response.status_code == 403
    finally:
        butler_sidecar.app.dependency_overrides.clear()


def test_invalid_canonical_snapshots_never_return_200():
    invalid = (
        LearningCapabilitySnapshot(
            generation=True,
            capabilities={
                "company_rules": CapabilityState.IN_USE,
                "company_facts": CapabilityState.IN_USE,
                "company_formats": CapabilityState.REGISTERED_ONLY,
                "folder_learning": CapabilityState.PREVIEW_ONLY,
            },
        ),
        LearningCapabilitySnapshot(
            generation=1,
            capabilities={
                "company_rules": CapabilityState.UNKNOWN,
                "company_facts": CapabilityState.IN_USE,
                "company_formats": CapabilityState.REGISTERED_ONLY,
                "folder_learning": CapabilityState.PREVIEW_ONLY,
            },
        ),
        LearningCapabilitySnapshot(
            generation=1,
            capabilities={
                "company_rules": CapabilityState.IN_USE,
                "company_facts": CapabilityState.IN_USE,
                "company_formats": CapabilityState.REGISTERED_ONLY,
                "folder_learning": CapabilityState.PREVIEW_ONLY,
                "extra": CapabilityState.IN_USE,
            },
        ),
    )
    try:
        with TestClient(butler_sidecar.app) as client:
            for snapshot in invalid:
                _override(_InvalidSnapshotService(snapshot))
                response = client.get(
                    "/api/capabilities/learning",
                    headers=_request_headers(),
                )
                assert response.status_code != 200
                assert response.json()["source"] == "UNAVAILABLE"
    finally:
        butler_sidecar.app.dependency_overrides.clear()


def test_every_learning_response_has_noncache_and_nosniff_headers():
    cases = (
        (_SuccessService(), _request_headers, 200),
        (_UnavailableService(), _request_headers, 503),
    )
    try:
        with TestClient(butler_sidecar.app) as client:
            for service, headers_factory, expected in cases:
                _override(service)
                response = client.get(
                    "/api/capabilities/learning",
                    headers=headers_factory(),
                )
                assert response.status_code == expected
                assert response.headers["cache-control"] == "no-store"
                assert response.headers["pragma"] == "no-cache"
                assert response.headers["x-content-type-options"] == "nosniff"

            for headers, expected in (
                (
                    {"Host": "testserver", "Origin": "tauri://localhost"},
                    401,
                ),
                (
                    {
                        "Authorization": "Bearer invalid",
                        "Host": "testserver",
                        "Origin": "tauri://localhost",
                    },
                    403,
                ),
                ({**_request_headers(), "Host": "example.invalid"}, 400),
                (
                    {
                        **_request_headers(),
                        "Origin": "https://example.invalid",
                    },
                    403,
                ),
            ):
                response = client.get(
                    "/api/capabilities/learning",
                    headers=headers,
                )
                assert response.status_code == expected
                assert response.headers["cache-control"] == "no-store"
                assert response.headers["pragma"] == "no-cache"
                assert response.headers["x-content-type-options"] == "nosniff"
    finally:
        butler_sidecar.app.dependency_overrides.clear()


def test_internal_errors_do_not_expose_source_paths_or_user_values(caplog):
    _override(_SensitiveFailureService())
    try:
        with TestClient(butler_sidecar.app) as client:
            response = client.get(
                "/api/capabilities/learning",
                headers=_request_headers(),
            )
        combined = response.text + "\n".join(
            record.getMessage() for record in caplog.records
        )
        assert response.status_code == 503
        assert "/Users/" not in combined
        assert "private-user" not in combined
        assert "customer-contract" not in combined
    finally:
        butler_sidecar.app.dependency_overrides.clear()
