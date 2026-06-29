"""수정1 검증 — 박스5 회계 SSE digest-only usage_log.

필수 테스트:
  · SSE 비버퍼링: /accounting/classify 는 미들웨어 _ROUTE_MAP 에 없고, 스트림 순서가
    phase_start … complete 로 유지된다(버퍼링/가로채기 0).
  · complete 이후 digest-only usage_log 1건 생성(background).
  · digest-only: 원문(summary 내용)·파일명·temp path 가 record 어디에도 없다.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from butler_pc_core.sidecar.middleware import usage_accumulator as ua
from butler_pc_core.sidecar.middleware.usage_accumulator import (
    ACCOUNTING_ENDPOINT,
    build_accounting_usage_log,
    get_store,
    record_accounting_usage,
)

try:
    from fastapi.testclient import TestClient  # noqa: F401

    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

_skip = pytest.mark.skipif(not _DEPS_OK, reason="fastapi 미설치")


# ── 테스트1-a: 미들웨어가 회계 SSE 를 버퍼링하지 않는다(구조적 보증) ───────────
def test_accounting_route_excluded_from_route_map():
    assert "/accounting/classify" not in ua._ROUTE_MAP
    # 미들웨어가 버퍼링하는 라우트는 모두 JSON 전용이어야 한다(회계 endpoint 미포함).
    for _intent, _box, endpoint in ua._ROUTE_MAP.values():
        assert endpoint != ACCOUNTING_ENDPOINT


# ── 테스트1-b: SSE 스트림 순서 유지(phase_start … complete) ────────────────────
@_skip
@pytest.mark.active_policy
def test_accounting_sse_stream_order_intact(monkeypatch):
    """엔드포인트 SSE 가 깨지지 않고 complete 가 마지막 이벤트로 도착한다."""
    monkeypatch.setenv("BUTLER_USAGE_LOG_DISABLE_PERSIST", "1")  # 테스트 파일 사이드이펙트 0
    # active_policy 부트스트랩 후 sidecar import (conftest 가 처리).
    pytest.importorskip("pandas")
    from butler_sidecar import app

    client = TestClient(app)
    csv = "적요,거래처,금액\n급여 지급,,1000000\n통신비 납부,KT,88000\n".encode("utf-8")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(csv)
        csv_path = f.name
    try:
        with open(csv_path, "rb") as fp:
            resp = client.post(
                "/accounting/classify",
                files={"file": ("test.csv", fp, "text/csv")},
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200
    finally:
        Path(csv_path).unlink(missing_ok=True)

    events = [ln[6:].strip() for ln in resp.text.splitlines() if ln.startswith("event:")]
    assert "phase_start" in events
    assert events[-1] == "complete", f"complete 가 마지막 이벤트여야 함: {events}"
    # 스트리밍이 버퍼링되지 않았다면 phase_start 가 complete 보다 먼저 온다.
    assert events.index("phase_start") < events.index("complete")


# ── 테스트2+3: record_accounting_usage — 1건·digest-only·schema-valid ──────────
def test_record_accounting_usage_one_digest_only_record():
    store = ua.UsageLogStore()
    secret = "급여 1,200만원 — 절대 원문 저장 금지 SENTINEL"
    summary = {"total_rows": 2, "company_knowledge": secret, "avg_confidence": 0.91}

    rec = record_accounting_usage(
        result_id="rid-xyz", summary=summary, latency_ms=33.3, store=store
    )

    # complete 이후 usage_log 정확히 1건.
    assert rec is not None
    assert len(store.records) == 1
    assert store.records[0] is rec

    # 회계 라우트 정합 + real 불변식.
    assert rec["intent_label"] == "accounting_classify"
    assert rec["box_id"] == "5"
    assert rec["endpoint"] == "POST /accounting/classify"
    assert rec["integration_mode"] == "real"
    assert rec["real_validation_done"] is True
    assert rec["policy_decision"] == "allow"
    assert rec["retention_class"] == "audit_digest_only"

    # digest-only: 원문(summary 내용)이 record 어디에도 없다.
    blob = json.dumps(rec, ensure_ascii=False)
    assert secret not in blob
    assert "1,200만원" not in blob
    assert "company_knowledge" not in blob
    assert "rid-xyz" not in blob  # result_id 원문도 digest 로만
    # digest 필드는 sha256 패턴.
    assert rec["result_digest"].startswith("sha256:")
    assert rec["request_digest"].startswith("sha256:")


def test_schema_invalid_accounting_record_not_stored():
    """스키마 검증 실패 레코드는 저장하지 않는다(fail-closed)."""
    store = ua.UsageLogStore()

    def _bad_builder(**_kwargs):
        rec = build_accounting_usage_log(result_id="r", summary={"total_rows": 1}, latency_ms=1.0)
        rec["box_id"] = "helper1"  # accounting_classify ↔ box_id 불일치 → 스키마 실패
        return rec

    # build 를 invalid 로 치환해 record_accounting_usage 의 검증 분기를 강제.
    import butler_pc_core.sidecar.middleware.usage_accumulator as mod

    orig = mod.build_accounting_usage_log
    mod.build_accounting_usage_log = _bad_builder
    try:
        rec = record_accounting_usage(
            result_id="r", summary={"total_rows": 1}, latency_ms=1.0, store=store
        )
    finally:
        mod.build_accounting_usage_log = orig

    assert rec is None
    assert len(store.records) == 0
    assert store.dropped == 1


# ── 테스트2(배경 결정성): complete 후 background 스케줄러가 usage_log 1건 기록 ──
def test_schedule_accounting_usage_log_background_records(monkeypatch):
    monkeypatch.setenv("BUTLER_USAGE_LOG_DISABLE_PERSIST", "1")  # 파일 사이드이펙트 0
    import butler_sidecar

    get_store().clear()

    async def _drive():
        butler_sidecar._schedule_accounting_usage_log(
            "rid-bg", {"total_rows": 3, "company_knowledge": "내부 비밀"}, 12.0
        )
        await asyncio.sleep(0)
        pending = list(butler_sidecar._ACCOUNTING_USAGE_TASKS)
        if pending:
            await asyncio.gather(*pending)

    asyncio.run(_drive())

    records = get_store().records
    assert len(records) == 1
    assert records[0]["intent_label"] == "accounting_classify"
    assert records[0]["box_id"] == "5"
    # 원문 누출 0.
    assert "내부 비밀" not in json.dumps(records[0], ensure_ascii=False)
