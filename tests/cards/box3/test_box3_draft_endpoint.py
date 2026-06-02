from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.sidecar.routes.box3_draft import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_box3_draft_endpoint_returns_required_contract():
    response = _client().post(
        "/v1/cards/3/draft",
        json={
            "input_text": "2025년 1분기 영업 보고. 매출 50억원 달성. 신규 고객 30개사 확보.",
            "prompt_template": "다음 보고서를 참고하여 2분기 영업 계획 초안을 작성하세요\n\n{input}",
            "max_new_tokens": 300,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["external_send_zero"] is True
    assert data["raw_saved_zero"] is True
    assert data["raw_doc_logged"] is False
    assert data["contract_only"] is True
    assert data["model_chain"] == ["base", "butler_v3", "tool_call", "box3_smoke"]
    assert data["request_digest"].startswith("sha256:")
    assert "매출 50억원" not in data["request_digest"]
    assert data["inference_config"]["repetition_penalty"] >= 1.2
    assert data["inference_config"]["no_repeat_ngram_size"] == 3
    assert data["sealed_sha"]["box3_smoke"] == "4d86414ddf74b048d6db011659e4227641257ad0d931faab690dcddeea58cf74"


def test_box3_draft_endpoint_rejects_non_localhost(monkeypatch):
    import butler_pc_core.sidecar.routes.box3_draft as mod
    monkeypatch.setattr(mod, "is_localhost_request", lambda request: False)
    response = _client().post(
        "/v1/cards/3/draft",
        json={"input_text": "x", "prompt_template": "요약하세요", "max_new_tokens": 50},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["fail_class"] == "LOCALHOST_ONLY"


def test_box3_draft_endpoint_validates_empty_input():
    response = _client().post(
        "/v1/cards/3/draft",
        json={"input_text": "", "prompt_template": "요약하세요"},
    )
    assert response.status_code == 422


def test_box3_draft_endpoint_clamps_max_new_tokens():
    response = _client().post(
        "/v1/cards/3/draft",
        json={"input_text": "본문", "prompt_template": "요약하세요", "max_new_tokens": 99999},
    )
    assert response.status_code == 422


def test_box3_real_route_is_contract_only_without_runner():
    response = _client().post(
        "/v1/cards/3/draft",
        json={
            "reference_docs": ["프로젝트 알파 납품 일정 표 | 납품일 2026년 3월 31일 | 계약 금액 1억원"],
            "drafting_request": "납품 보고서를 작성하라",
        },
    )
    assert response.status_code == 200
    data = response.json()
    # asset PENDING → real claim 닫힘(contract_only). raw 노출 0.
    assert data["status"] == "contract_only"
    assert data["contract_only"] is True and data["real_claim_allowed"] is False
    assert "draft_text" not in data["audit"]
    assert data["request_digest"].startswith("sha256:")


def test_box3_real_route_rejects_oversized_reference_doc():
    from butler_pc_core.sidecar.routes.box3_draft import MAX_REFERENCE_LENGTH

    response = _client().post(
        "/v1/cards/3/draft",
        json={
            "reference_docs": ["가" * (MAX_REFERENCE_LENGTH + 1)],
            "drafting_request": "요약",
        },
    )
    assert response.status_code == 422
