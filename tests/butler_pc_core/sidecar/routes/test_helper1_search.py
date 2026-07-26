"""Helper1 product path must fail closed when verified assets are unavailable."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytestmark = pytest.mark.active_policy


def _load_sidecar():
    import butler_sidecar

    if not getattr(butler_sidecar, "_FASTAPI_AVAILABLE", False):
        pytest.skip("FastAPI not available in butler_sidecar")
    return butler_sidecar


def _client_and_token():
    from fastapi.testclient import TestClient

    mod = _load_sidecar()
    token = mod._TOKEN_MANAGER.generate()
    return TestClient(mod.app), token


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_search_asset_absent_returns_stable_503(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1
    from butler_pc_core.assets.errors import AssetError

    class MissingAssets:
        @staticmethod
        def find(_query, _top_k):
            raise AssetError("REQUIRED_ASSET_MISSING")

    monkeypatch.setattr(h1, "_load_memory_helper", lambda: MissingAssets)
    client, token = _client_and_token()
    response = client.post(
        "/v1/helpers/1/search",
        json={"query": "test"},
        headers=_headers(token),
    )
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == {
        "ok": False,
        "code": "ASSET_UNAVAILABLE",
        "capability": "helper1.search",
        "retryable": False,
    }


def test_ask_asset_absent_returns_stable_503(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1
    from butler_pc_core.assets.errors import AssetError

    class MissingAssets:
        @staticmethod
        def ask(_query):
            raise AssetError("REQUIRED_ASSET_MISSING")

    monkeypatch.setattr(h1, "_load_memory_helper", lambda: MissingAssets)
    client, token = _client_and_token()
    response = client.post(
        "/v1/helpers/1/ask",
        json={"query": "test"},
        headers=_headers(token),
    )
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["capability"] == "helper1.ask"


@pytest.mark.parametrize("endpoint", ["search", "ask"])
def test_static_import_failure_returns_stable_503(endpoint, monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1

    def fail_import():
        raise ImportError("dependency unavailable")

    monkeypatch.setattr(h1, "_load_memory_helper", fail_import)
    client, token = _client_and_token()
    response = client.post(
        f"/v1/helpers/1/{endpoint}",
        json={"query": "test"},
        headers=_headers(token),
    )
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "ASSET_UNAVAILABLE"


def test_import_error_does_not_leak_raw_path(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1

    sentinel = "/" + "Users/SECRET_LOCAL_2026_05_27/broken_dep"

    def fail_import():
        raise ImportError(f"missing dependency at {sentinel}")

    monkeypatch.setattr(h1, "_load_memory_helper", fail_import)
    client, token = _client_and_token()
    response = client.post(
        "/v1/helpers/1/search",
        json={"query": "test"},
        headers=_headers(token),
    )
    assert response.status_code == 503, response.text
    assert sentinel not in response.text
