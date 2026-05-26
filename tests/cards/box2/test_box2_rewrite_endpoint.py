from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from butler_pc_core.sidecar.routes.box2_rewrite import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_box2_rewrite_endpoint_returns_required_contract():
    response = _client().post(
        "/v1/cards/2/rewrite",
        json={
            "foreign_doc": "제목: 공급 계약 초안\n발행일: 2026-05-26\n담당자: 김성훈\n합의사항: 월 1회 검토\n금액: 1,000만원",
            "our_format": "제목:\n발행일:\n담당자:\n핵심 내용:\n합의사항:\n금액/일정:\n확인 필요:\n최종 문안:",
            "options": {"tone": "company_standard", "preserve_numbers": True, "redact_sensitive": True},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["external_send_zero"] is True
    assert data["raw_saved_zero"] is True
    assert data["raw_doc_logged"] is False
    assert data["request_digest"].startswith("sha256:")
    assert data["model_chain"] == ["base", "butler_v3", "helper_3"]
    assert "공급 계약 초안" not in data["request_digest"]
    for section in ["제목:", "발행일:", "담당자:", "핵심 내용:", "합의사항:", "금액/일정:", "확인 필요:", "최종 문안:"]:
        assert section in data["rewritten_doc"]


def test_box2_rewrite_endpoint_rejects_non_localhost(monkeypatch):
    from butler_pc_core.sidecar.routes import box2_rewrite

    monkeypatch.setattr(box2_rewrite, "is_localhost_request", lambda request: False)
    response = _client().post(
        "/v1/cards/2/rewrite",
        json={"foreign_doc": "a", "our_format": "b"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["fail_class"] == "LOCALHOST_ONLY"


def test_box2_rewrite_endpoint_enforces_max_input_length():
    response = _client().post(
        "/v1/cards/2/rewrite",
        json={"foreign_doc": "x" * 12001, "our_format": "b"},
    )
    assert response.status_code == 422
