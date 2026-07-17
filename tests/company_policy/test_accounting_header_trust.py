"""RI-P0-002/013 — 회계검토 경로는 정책 결정 속성을 클라이언트 헤더에서 신뢰하지 않는다.

middleware 로직만 격리해 검증한다(정책 저장소·PolicyGate 는 stub). accounting mutation 경로에
x-user-role: admin 등 조작 헤더를 보내도 서버 고정 안전값(employee·restricted·학습불가·외부전송0)
이 envelope 로 들어가는지, 그리고 비-accounting 경로는 기존 동작(헤더 반영)이 보존되는지 본다.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from starlette.testclient import TestClient

from butler_pc_core.company_policy import middleware as mw


class _DummyGate:
    allowed = True
    audit_ref = "audit-ref"
    applied_policy_digest = None

    def to_dict(self):  # pragma: no cover - not reached when allowed
        return {}


class _Store:
    def load_active_policy(self):
        return object()  # non-None, non-error: middleware proceeds to envelope build


def _client(monkeypatch):
    captured: dict = {}

    def spy_envelope(**kwargs):
        captured.clear()
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(mw, "build_policy_task_envelope", spy_envelope)
    monkeypatch.setattr(mw.PolicyGate, "evaluate", staticmethod(lambda env, policy: _DummyGate()))

    app = FastAPI()
    mw.add_policy_gate_middleware(app, policy_store=_Store())

    @app.post("/v1/accounting/unaccounted/{txn_id}/assign")
    async def _assign(txn_id: str):
        return {"ok": True}

    @app.post("/v1/cards/2/rewrite")
    async def _rewrite():
        return {"ok": True}

    return TestClient(app), captured


_FORGED = {
    "x-user-role": "admin",
    "x-learning-allowed": "1",
    "x-retention-days": "3650",
    "x-doc-grade": "public",
    "x-external-send-requested": "1",
    "x-masking-requested": "0",
}


def test_accounting_route_ignores_forged_policy_headers(monkeypatch):
    client, captured = _client(monkeypatch)
    resp = client.post(
        "/v1/accounting/unaccounted/txn_1234567890123456/assign", headers=_FORGED
    )
    assert resp.status_code == 200
    # ★ 클라이언트가 admin·학습허용·장기보존·public·외부전송을 요청해도 서버 고정 안전값만 쓰인다.
    assert captured["user_role"] == "employee"
    assert captured["learning_allowed"] is False
    assert captured["retention_days"] == 30
    assert captured["doc_grade"] == "restricted"
    assert captured["external_send_requested"] is False
    assert captured["masking_requested"] is True


def test_non_accounting_route_still_reflects_headers(monkeypatch):
    client, captured = _client(monkeypatch)
    resp = client.post("/v1/cards/2/rewrite", headers={"x-user-role": "admin"})
    assert resp.status_code == 200
    # 비-accounting 경로는 기존 동작을 보존한다(별도 팀 과제로 남긴 RI-P0-002 전역 잔여).
    assert captured["user_role"] == "admin"
