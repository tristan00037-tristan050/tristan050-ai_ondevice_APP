"""test_sse_stream.py — SSE 진행률 스트림 테스트 (8 cases)."""
from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import patch

import pytest

try:
    from fastapi.testclient import TestClient
    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False

_skip_no_fastapi = pytest.mark.skipif(
    not _FASTAPI_OK, reason="fastapi 미설치 — SSE 테스트 건너뜀"
)


def _get_app_and_deps():
    from butler_sidecar import app, _active_controllers
    from butler_pc_core.runtime.timeout_controller import PartialResultError
    return app, _active_controllers, PartialResultError


def _parse_events(raw: str) -> list[dict[str, Any]]:
    """SSE raw text → list of {event, data} dicts."""
    events = []
    current: dict[str, str] = {}
    for line in raw.splitlines():
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.split(":", 1)[1].strip())
        elif line == "" and current:
            events.append(current.copy())
            current = {}
    if current:
        events.append(current)
    return events


_STREAM_PAYLOAD = {"file_path": "/tmp/test.txt", "total_chunks": 3, "output_dir": "/tmp"}


@pytest.fixture
def client_and_deps():
    app, controllers, PartialResultError = _get_app_and_deps()
    controllers.clear()
    client = TestClient(app)
    yield client, controllers, PartialResultError
    controllers.clear()


# ─────────────────────────────────────────────────────────────────────────────


@_skip_no_fastapi
def test_happy_normal_completion(client_and_deps):
    """정상 완료 시 phase_start → chunk_* × N → complete 이벤트 수신."""
    client, _, _ = client_and_deps
    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None), \
         patch("asyncio.wait_for", side_effect=lambda coro, timeout: coro):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = _parse_events(resp.text)
    event_types = [e["event"] for e in events]
    assert event_types[0] == "phase_start"
    assert "complete" in event_types
    assert "error" not in event_types


@_skip_no_fastapi
def test_happy_chunk_progress_order(client_and_deps):
    """chunk_progress 이벤트의 current 값이 1부터 total까지 순서대로 증가한다."""
    client, _, _ = client_and_deps
    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None), \
         patch("asyncio.wait_for", side_effect=lambda coro, timeout: coro):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    events = _parse_events(resp.text)
    progress = [e["data"]["current"] for e in events if e.get("event") == "chunk_progress"]
    assert progress == list(range(1, _STREAM_PAYLOAD["total_chunks"] + 1))


@_skip_no_fastapi
def test_boundary_heartbeat_event_present_after_idle(client_and_deps):
    """last_event_time 조작으로 heartbeat 경로가 실행되는지 확인한다."""
    client, _, _ = client_and_deps
    original_monotonic = time.monotonic
    call_count = [0]

    def _fake_monotonic():
        call_count[0] += 1
        base = original_monotonic()
        return base + (10.0 if call_count[0] > 5 else 0.0)

    with patch("butler_sidecar.time.monotonic", side_effect=_fake_monotonic), \
         patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None), \
         patch("asyncio.wait_for", side_effect=lambda coro, timeout: coro):
        resp = client.post(
            "/api/analyze/stream",
            json={"file_path": "/tmp/f.txt", "total_chunks": 1, "output_dir": "/tmp"},
        )

    events = _parse_events(resp.text)
    assert "heartbeat" in [e["event"] for e in events]


@_skip_no_fastapi
def test_boundary_concurrent_streams_get_distinct_task_ids(client_and_deps):
    """동시 스트림 요청은 서로 다른 task_id를 받는다."""
    client, _, _ = client_and_deps
    task_ids: list[str] = []
    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None), \
         patch("asyncio.wait_for", side_effect=lambda coro, timeout: coro):
        for _ in range(3):
            resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)
            task_ids.append(resp.headers.get("x-task-id", ""))

    assert len(set(task_ids)) == 3, "task_id 중복 발생"


@_skip_no_fastapi
def test_adv_chunk_timeout_to_cancelled(client_and_deps):
    """청크 타임아웃 발생 시 cancelled(chunk_timeout) 이벤트가 마지막에 온다."""
    client, _, PartialResultError = client_and_deps

    def _raise(*args, **kwargs):
        raise PartialResultError("[chunk_timeout] 45초 초과 → /tmp/p.json", "/tmp/p.json")

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", side_effect=_raise):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    last = _parse_events(resp.text)[-1]
    assert last["event"] == "cancelled"
    assert last["data"]["reason"] == "chunk_timeout"


@_skip_no_fastapi
def test_adv_hard_timeout_to_cancelled(client_and_deps):
    """하드 타임아웃 발생 시 cancelled(hard_timeout) 이벤트가 마지막에 온다."""
    client, _, PartialResultError = client_and_deps

    def _raise(*args, **kwargs):
        raise PartialResultError("[hard_timeout] 180초 초과 → /tmp/p.json", "/tmp/p.json")

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", side_effect=_raise):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    last = _parse_events(resp.text)[-1]
    assert last["event"] == "cancelled"
    assert last["data"]["reason"] == "hard_timeout"


@_skip_no_fastapi
def test_adv_user_cancel_cleans_up_controller(client_and_deps):
    """스트림 완료 후 _active_controllers 에서 task_id가 제거된다."""
    client, controllers, PartialResultError = client_and_deps

    def _raise(*args, **kwargs):
        raise PartialResultError("[cancelled] 작업 취소 → /tmp/p.json", "/tmp/p.json")

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", side_effect=_raise):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)
        tid = resp.headers.get("x-task-id", "unknown")

    last = _parse_events(resp.text)[-1]
    assert last["event"] == "cancelled"
    assert last["data"]["reason"] == "user_cancel"
    assert tid not in controllers


@_skip_no_fastapi
def test_adv_unserializable_chunk_safe(client_and_deps):
    """직렬화 불가 예외가 발생해도 error 이벤트로 안전하게 처리된다."""
    client, _, _ = client_and_deps

    class _BadError(Exception):
        pass

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", side_effect=_BadError("broken")):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    assert any(e["event"] == "error" for e in _parse_events(resp.text))
