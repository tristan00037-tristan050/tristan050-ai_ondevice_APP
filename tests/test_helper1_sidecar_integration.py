from __future__ import annotations

import pytest

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
    return TestClient(mod.app), token, mod


def test_helper1_endpoints_registered():
    mod = _load_sidecar()
    paths = {getattr(r, "path", None) for r in mod.app.routes}
    assert "/v1/helpers/1/search" in paths
    assert "/v1/helpers/1/ask" in paths


def test_helper1_search_post_200():
    client, token, _ = _client_and_token()
    resp = client.post(
        "/v1/helpers/1/search",
        json={"query": "지난 분기 매출 보고 어디 있었지", "top_k": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["integration_mode"] in ("real", "contract_only")
    assert data["external_send_zero"] is True
    assert data["raw_text_logged"] is False
    assert data["audit"]["query_digest"].startswith("sha256:")
    if data["integration_mode"] == "contract_only":
        assert data["real_validation_done"] is False
        assert data["results"] == []


def test_helper1_ask_post_200():
    client, token, _ = _client_and_token()
    resp = client.post(
        "/v1/helpers/1/ask",
        json={"query": "내가 작년에 정리한 보안 정책 요약해줘"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["integration_mode"] in ("real", "contract_only")
    assert data["external_send_zero"] is True
    assert data["raw_text_logged"] is False
    if data["integration_mode"] == "contract_only":
        assert data["answer"] == "contract_only_response"
        assert data["sources"] == []
        assert data["real_validation_done"] is False


def test_helper1_audit_has_no_raw_text():
    client, token, _ = _client_and_token()
    secret_query = "UNIQUE_SECRET_QUERY_STRING_12345"
    resp = client.post(
        "/v1/helpers/1/ask",
        json={"query": secret_query},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    audit = resp.json()["audit"]
    assert secret_query not in str(audit)
    assert set(audit.keys()) == {"query_digest", "policy_decision", "reason"}


def test_box2_box3_routes_not_regressed():
    mod = _load_sidecar()
    paths = {getattr(r, "path", None) for r in mod.app.routes}
    assert "/v1/cards/2/rewrite" in paths
    assert "/v1/cards/3/draft" in paths


def test_helper1_search_rejects_non_localhost(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1
    monkeypatch.setattr(h1, "is_localhost_request", lambda request: False)
    client, token, _ = _client_and_token()
    resp = client.post(
        "/v1/helpers/1/search",
        json={"query": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["fail_class"] == "LOCALHOST_ONLY"


def test_helper1_requires_capability_token():
    mod = _load_sidecar()
    from fastapi.testclient import TestClient
    mod._TOKEN_MANAGER.generate()
    client = TestClient(mod.app)
    resp = client.post("/v1/helpers/1/search", json={"query": "x"})
    assert resp.status_code in (401, 403), resp.text


def test_helper1_rejects_bad_capability_token():
    mod = _load_sidecar()
    from fastapi.testclient import TestClient
    mod._TOKEN_MANAGER.generate()
    client = TestClient(mod.app)
    resp = client.post(
        "/v1/helpers/1/ask",
        json={"query": "x"},
        headers={"Authorization": "Bearer wrong-token-value"},
    )
    assert resp.status_code in (401, 403), resp.text


def test_helper1_blocks_non_localhost(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1
    monkeypatch.setattr(h1, "is_localhost_request", lambda request: False)
    client, token, _ = _client_and_token()
    resp = client.post(
        "/v1/helpers/1/ask",
        json={"query": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["fail_class"] == "LOCALHOST_ONLY"


def test_helper1_contract_only_does_not_call_sdk(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1

    def _boom(*a, **k):
        raise AssertionError("SDK must not be loaded in contract_only mode")

    monkeypatch.setattr(h1, "integration_mode", lambda: "contract_only")
    monkeypatch.setattr(h1, "_load_memory_helper", _boom)
    client, token, _ = _client_and_token()
    resp = client.post(
        "/v1/helpers/1/ask",
        json={"query": "회사 정책 요약"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["integration_mode"] == "contract_only"
    assert data["real_validation_done"] is False
    assert data["answer"] == "contract_only_response"


def test_helper1_real_mode_offload(monkeypatch):
    import butler_pc_core.sidecar.routes.helper1_search as h1

    class _FakeMH:
        @staticmethod
        def find(query, top_k=5):
            return [{"chunk_id": "c1", "score": 0.9}]

        @staticmethod
        def ask(query):
            return {"answer": "real-answer", "sources": [{"chunk_id": "c1", "score": 0.9}]}

    monkeypatch.setattr(h1, "integration_mode", lambda: "real")
    monkeypatch.setattr(h1, "_load_memory_helper", lambda: _FakeMH)
    client, token, _ = _client_and_token()

    s = client.post("/v1/helpers/1/search", json={"query": "q", "top_k": 3}, headers={"Authorization": f"Bearer {token}"})
    assert s.status_code == 200, s.text
    sd = s.json()
    assert sd["integration_mode"] == "real"
    assert sd["real_validation_done"] is True
    assert sd["results"][0]["chunk_id"] == "c1"
    assert sd["results"][0]["source_digest"].startswith("sha256:")

    a = client.post("/v1/helpers/1/ask", json={"query": "q"}, headers={"Authorization": f"Bearer {token}"})
    assert a.status_code == 200, a.text
    ad = a.json()
    assert ad["integration_mode"] == "real"
    assert ad["real_validation_done"] is True
    assert ad["answer"] == "real-answer"


def test_helper1_search_uses_anyio_offload_in_source():
    import inspect
    import butler_pc_core.sidecar.routes.helper1_search as h1
    source = inspect.getsource(h1)
    assert "anyio.to_thread.run_sync" in source
    assert "raw_results = mh.find(payload.query" not in source
    assert "produced = mh.ask(payload.query)" not in source
