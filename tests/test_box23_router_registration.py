from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytestmark = pytest.mark.active_policy


def _load_app():
    import butler_sidecar
    if not getattr(butler_sidecar, "_FASTAPI_AVAILABLE", False):
        pytest.skip("FastAPI not available in butler_sidecar")
    return butler_sidecar


def test_box2_box3_routes_registered_in_production_sidecar():
    mod = _load_app()
    paths = {getattr(r, "path", None) for r in mod.app.routes}
    assert "/v1/cards/2/rewrite" in paths
    assert "/v1/cards/3/draft" in paths


def test_existing_routes_not_regressed():
    mod = _load_app()
    paths = {getattr(r, "path", None) for r in mod.app.routes}
    for existing in [
        "/health",
        "/api/sidecar/health",
        "/accounting/classify",
        "/api/document_transform/compose",
        "/request_parsing/parse",
    ]:
        assert existing in paths, f"regressed: {existing} missing"


def test_box3_draft_endpoint_200_with_capability_token():
    mod = _load_app()
    from fastapi.testclient import TestClient

    token = mod._TOKEN_MANAGER.generate()
    client = TestClient(mod.app)
    resp = client.post(
        "/v1/cards/3/draft",
        json={
            "input_text": "2025년 1분기 매출 50억원 달성. 신규 고객 30개사.",
            "prompt_template": "다음 보고서를 참고하여 2분기 계획 초안을 작성하세요\n\n{input}",
            "max_new_tokens": 100,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["contract_only"] is True
    assert data["model_chain"] == ["base", "butler_v3", "tool_call", "box3_smoke"]
    assert data["inference_config"]["repetition_penalty"] >= 1.2
    assert data["inference_config"]["no_repeat_ngram_size"] == 3
    assert data["external_send_zero"] is True


def test_box2_rewrite_endpoint_200_with_capability_token():
    mod = _load_app()
    from fastapi.testclient import TestClient

    token = mod._TOKEN_MANAGER.generate()
    client = TestClient(mod.app)
    resp = client.post(
        "/v1/cards/2/rewrite",
        json={
            "foreign_doc": "제목: 공급 계약 초안\n금액: 1000만원",
            "our_format": "제목:\n금액/일정:\n최종 문안:",
            "options": {"tone": "company_standard", "preserve_numbers": True, "redact_sensitive": True},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["external_send_zero"] is True
