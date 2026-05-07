"""test_sse_phase_messages.py — SSE phase_start 이벤트 메시지 정확성 검증."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

_skip = pytest.mark.skipif(not _DEPS_OK, reason="fastapi 미설치")

_CSV = "적요,거래처,금액\n급여 지급,,1000000\n통신비 납부,KT,88000\n".encode("utf-8")

EXPECTED_PHASE_1 = "분류 중 — 회계과목 매칭"
EXPECTED_PHASE_2 = "보고서 생성 중 — 요약 집계"


def _classify_and_collect_sse_events() -> list[dict]:
    """CSV 분류 요청을 수행하고 모든 SSE 이벤트를 dict 목록으로 반환."""
    from butler_sidecar import app

    client = TestClient(app)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(_CSV)
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

    events = []
    current_event = None
    for line in resp.text.splitlines():
        if line.startswith("event:"):
            current_event = line[6:].strip()
        elif line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
                if current_event:
                    events.append({"event": current_event, "data": data})
                    current_event = None
            except json.JSONDecodeError:
                pass
    return events


@_skip
def test_sse_emits_first_phase_start_message():
    """SSE 스트림에서 '분류 중 — 회계과목 매칭' phase_start 이벤트가 반드시 포함되어야 한다."""
    events = _classify_and_collect_sse_events()
    phase_messages = [
        e["data"].get("status_message", "")
        for e in events
        if e["event"] == "phase_start"
    ]
    assert EXPECTED_PHASE_1 in phase_messages, (
        f"'{EXPECTED_PHASE_1}' phase_start 메시지 없음. 수신된 메시지: {phase_messages}"
    )


@_skip
def test_sse_emits_second_phase_start_message():
    """SSE 스트림에서 '보고서 생성 중 — 요약 집계' phase_start 이벤트가 반드시 포함되어야 한다."""
    events = _classify_and_collect_sse_events()
    phase_messages = [
        e["data"].get("status_message", "")
        for e in events
        if e["event"] == "phase_start"
    ]
    assert EXPECTED_PHASE_2 in phase_messages, (
        f"'{EXPECTED_PHASE_2}' phase_start 메시지 없음. 수신된 메시지: {phase_messages}"
    )


@_skip
def test_sse_phase_start_order_is_correct():
    """phase_start 이벤트 순서: '분류 중' → '보고서 생성 중' → 'complete' 이어야 한다."""
    events = _classify_and_collect_sse_events()
    phase_starts = [
        e["data"].get("status_message", "")
        for e in events
        if e["event"] == "phase_start"
    ]
    assert len(phase_starts) >= 2, f"phase_start 이벤트가 2개 이상이어야 함: {phase_starts}"
    assert phase_starts[0] == EXPECTED_PHASE_1, (
        f"첫 번째 phase_start 메시지 불일치: '{phase_starts[0]}' (기대: '{EXPECTED_PHASE_1}')"
    )
    assert phase_starts[1] == EXPECTED_PHASE_2, (
        f"두 번째 phase_start 메시지 불일치: '{phase_starts[1]}' (기대: '{EXPECTED_PHASE_2}')"
    )

    # complete 이벤트가 맨 마지막이어야 함
    last_event = events[-1]["event"]
    assert last_event == "complete", f"마지막 이벤트가 'complete'가 아님: '{last_event}'"
