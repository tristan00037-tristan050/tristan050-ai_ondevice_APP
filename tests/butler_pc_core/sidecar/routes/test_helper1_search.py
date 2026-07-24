"""Codex P2 regression guard (2026-05-27) for helper1_search sidecar router.

#1: SDK 부재 시 핸들러가 HTTP 200 + empty/stub("blocked" mode)로 새던 것을 차단 —
    contract 모드(real/contract_only) 안의 honest contract_only로 귀결.
#2: SDK 파일은 있으나 import가 실패할 때 HTTP 500 대신 contract_only로 downgrade,
    raw 에러 메시지/경로 노출 0 (error_class + digest만).
"""
from __future__ import annotations

import pytest

# v3.2-R gate fix (fixture drift): the fail-closed company-policy gate
# (POLICY_BOOTSTRAP_REQUIRED, added in #826/#844/#866) now requires an ACTIVE
# policy; opt into the existing conftest bootstrap fixture.
pytestmark = pytest.mark.active_policy

pytest.importorskip("fastapi")


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


# ── 결함 #1 — SDK 부재가 stub(200/blocked)이 아니라 contract_only로 귀결 ──

def test_search_sdk_absent_returns_contract_only(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1
    monkeypatch.setattr(h1, "_sdk_present", lambda: False)
    client, token = _client_and_token()
    resp = client.post("/v1/helpers/1/search", json={"query": "test"}, headers=_headers(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["integration_mode"] == "contract_only", data
    assert data["integration_mode"] != "blocked"
    assert data["real_validation_done"] is False
    assert data["results"] == []


def test_ask_sdk_absent_returns_contract_only(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1
    monkeypatch.setattr(h1, "_sdk_present", lambda: False)
    client, token = _client_and_token()
    resp = client.post("/v1/helpers/1/ask", json={"query": "test"}, headers=_headers(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["integration_mode"] == "contract_only", data
    assert data["real_validation_done"] is False
    assert data["answer"] == "contract_only_response"
    assert data["sources"] == []


# ── 결함 #2 — SDK import 실패가 HTTP 500이 아니라 contract_only downgrade ──

def test_search_sdk_import_failure_downgrades_to_contract_only(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1
    monkeypatch.setattr(h1, "_sdk_present", lambda: True)
    monkeypatch.setattr(h1, "_search_assets_present", lambda: True)

    def _boom():
        raise ImportError("dep missing")

    monkeypatch.setattr(h1, "_load_memory_helper", _boom)
    client, token = _client_and_token()
    resp = client.post("/v1/helpers/1/search", json={"query": "test"}, headers=_headers(token))
    assert resp.status_code != 500, f"import 실패에 HTTP 500 잔존: {resp.status_code}"
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["integration_mode"] == "contract_only", data
    assert data["real_validation_done"] is False
    assert data["sdk_import_failure"]["error_class"] == "ImportError"
    assert len(data["sdk_import_failure"]["error_digest"]) == 16


def test_ask_sdk_import_failure_downgrades_to_contract_only(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1
    monkeypatch.setattr(h1, "_sdk_present", lambda: True)
    monkeypatch.setattr(h1, "_ask_assets_present", lambda: True)

    def _boom():
        raise ImportError("dep missing")

    monkeypatch.setattr(h1, "_load_memory_helper", _boom)
    client, token = _client_and_token()
    resp = client.post("/v1/helpers/1/ask", json={"query": "test"}, headers=_headers(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["integration_mode"] == "contract_only"
    assert data["answer"] == "contract_only_response"


def test_sdk_import_error_does_not_leak_raw_path(monkeypatch):
    """import error의 raw 메시지/경로가 응답에 노출 0 (PR #755 no-raw-output 정합)."""
    import butler_pc_core.sidecar.routes.helper1_search as h1
    sentinel = "/Users/SECRET_LOCAL_2026_05_27/broken_dep"
    monkeypatch.setattr(h1, "_sdk_present", lambda: True)
    monkeypatch.setattr(h1, "_search_assets_present", lambda: True)

    def _boom():
        raise ImportError(f"missing dep at {sentinel}")

    monkeypatch.setattr(h1, "_load_memory_helper", _boom)
    client, token = _client_and_token()
    resp = client.post("/v1/helpers/1/search", json={"query": "test"}, headers=_headers(token))
    assert resp.status_code == 200, resp.text
    assert sentinel not in resp.text, f"raw local path가 응답에 노출됨: {resp.text}"
