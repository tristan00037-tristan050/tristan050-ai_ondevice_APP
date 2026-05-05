"""test_sse_stream.py — SSE 진행률 스트림 테스트 (11 cases)."""
from __future__ import annotations

import json
import time
from pathlib import Path
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
    from butler_pc_core.runtime.timeout_controller import (
        ChunkTimeoutError,
        HardTimeoutError,
        UserCancelledError,
    )
    return app, _active_controllers, ChunkTimeoutError, HardTimeoutError, UserCancelledError


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
_PARTIAL_PATH = Path("/tmp/p.json")


@pytest.fixture
def client_and_deps():
    app, controllers, ChunkTimeoutError, HardTimeoutError, UserCancelledError = _get_app_and_deps()
    controllers.clear()
    import butler_sidecar as _sidecar
    from butler_pc_core.inference.llm_runtime import LlmRuntime as _LlmRuntime
    _sidecar._SHARED_LLM = _LlmRuntime(model_path=None)
    client = TestClient(app)
    yield client, controllers, ChunkTimeoutError, HardTimeoutError, UserCancelledError
    controllers.clear()


# ─────────────────────────────────────────────────────────────────────────────


@_skip_no_fastapi
def test_happy_normal_completion(client_and_deps):
    """정상 완료 시 phase_start → chunk_* × N → complete 이벤트 수신."""
    client, *_ = client_and_deps
    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = _parse_events(resp.text)
    event_types = [e["event"] for e in events]
    assert "phase_start" in event_types
    assert "complete" in event_types
    assert "error" not in event_types


@_skip_no_fastapi
def test_happy_chunk_progress_order(client_and_deps):
    """chunk_progress 이벤트의 current 값이 1부터 total까지 순서대로 증가한다."""
    client, *_ = client_and_deps
    _form = {"file_path": "/tmp/test.txt", "total_chunks": "3", "output_dir": "/tmp"}
    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None):
        resp = client.post("/api/analyze/stream", data=_form)

    events = _parse_events(resp.text)
    progress = [e["data"]["current"] for e in events if e.get("event") == "chunk_progress"]
    assert progress == list(range(1, int(_form["total_chunks"]) + 1))


@_skip_no_fastapi
def test_boundary_chunk_events_present_during_streaming(client_and_deps):
    """스트리밍 중 chunk 이벤트가 포함되어야 한다 (토큰 스트림이 heartbeat를 대체)."""
    client, *_ = client_and_deps
    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None):
        resp = client.post(
            "/api/analyze/stream",
            json={"file_path": "/tmp/f.txt", "total_chunks": 1, "output_dir": "/tmp"},
        )

    events = _parse_events(resp.text)
    event_types = [e["event"] for e in events]
    # 스트리밍 모드: chunk 이벤트가 존재하고 heartbeat는 더 이상 사용되지 않음
    assert "chunk" in event_types, f"chunk 이벤트 없음: {event_types}"


@_skip_no_fastapi
def test_boundary_concurrent_streams_get_distinct_task_ids(client_and_deps):
    """동시 스트림 요청은 서로 다른 task_id를 받는다."""
    client, *_ = client_and_deps
    task_ids: list[str] = []
    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None):
        for _ in range(3):
            resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)
            task_ids.append(resp.headers.get("x-task-id", ""))

    assert len(set(task_ids)) == 3, "task_id 중복 발생"


@_skip_no_fastapi
def test_adv_chunk_timeout_to_cancelled(client_and_deps):
    """ChunkTimeoutError 발생 시 cancelled(chunk_timeout) 이벤트가 마지막에 온다."""
    client, _, ChunkTimeoutError, *_ = client_and_deps

    def _raise(*args, **kwargs):
        raise ChunkTimeoutError("[chunk_timeout] 45초 초과", _PARTIAL_PATH)

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", side_effect=_raise):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    last = _parse_events(resp.text)[-1]
    assert last["event"] == "cancelled"
    assert last["data"]["reason"] == "chunk_timeout"


@_skip_no_fastapi
def test_adv_hard_timeout_to_cancelled(client_and_deps):
    """HardTimeoutError 발생 시 cancelled(hard_timeout) 이벤트가 마지막에 온다."""
    client, _, _, HardTimeoutError, _ = client_and_deps

    def _raise(*args, **kwargs):
        raise HardTimeoutError("[hard_timeout] 180초 초과", _PARTIAL_PATH)

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", side_effect=_raise):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    last = _parse_events(resp.text)[-1]
    assert last["event"] == "cancelled"
    assert last["data"]["reason"] == "hard_timeout"


@_skip_no_fastapi
def test_adv_user_cancel_cleans_up_controller(client_and_deps):
    """스트림 완료 후 _active_controllers 에서 task_id가 제거된다."""
    client, controllers, _, _, UserCancelledError = client_and_deps

    def _raise(*args, **kwargs):
        raise UserCancelledError("[cancelled] 작업 취소", _PARTIAL_PATH)

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
    client, *_ = client_and_deps

    class _BadError(Exception):
        pass

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", side_effect=_BadError("broken")):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    assert any(e["event"] == "error" for e in _parse_events(resp.text))


# ─────────────── 회귀 테스트 (P1 + P2 결함 재발 방지) ────────────────────────


@_skip_no_fastapi
def test_adv_chunk_timeout_actually_cancels_slow_chunk(client_and_deps):
    """결함 1 회귀: 청크 작업이 chunk_timeout 초과 시 실제로 취소된다.

    generate_stream_with_cancel을 cancel_event 대기 slow 제너레이터로 교체하고
    chunk_timeout=2초로 단축 → 2초 내에 cancelled(chunk_timeout)이 발생하는지 검증.
    60초를 실제로 기다리면 결함이 재발한 것이다.
    """
    from butler_pc_core.runtime.timeout_controller import TimeoutController as TC
    from butler_pc_core.inference.llm_runtime import LlmRuntime as _LR

    client, *_ = client_and_deps

    def _slow_streaming_gen(self, prompt, cancel_event, max_tokens=512, temperature=0.2, stop=None):
        # cancel_event가 설정될 때까지 대기 (최대 60초)
        cancel_event.wait(timeout=60)
        # 취소됐으면 토큰 없이 종료
        return
        yield  # 제너레이터 함수로 만들기 위한 unreachable yield

    class _FastTC(TC):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.chunk_timeout = 2.0

    start = time.time()
    with patch("butler_sidecar.TimeoutController", _FastTC), \
         patch.object(_LR, "generate_stream_with_cancel", _slow_streaming_gen):
        resp = client.post(
            "/api/analyze/stream",
            json={"file_path": "/tmp/f.txt", "total_chunks": 1, "output_dir": "/tmp"},
        )
    elapsed = time.time() - start

    # 본질 검증 1: 2초 여유(+3s) 안에 완료되어야 함 (60초 기다리면 결함)
    assert elapsed < 5, f"chunk_timeout이 작동 안 함 — {elapsed:.1f}초 걸림"

    # 본질 검증 2: cancelled 이벤트 reason이 chunk_timeout
    events = _parse_events(resp.text)
    cancelled = [e for e in events if e.get("event") == "cancelled"]
    assert len(cancelled) == 1, f"cancelled 이벤트 없음: {[e['event'] for e in events]}"
    assert cancelled[0]["data"]["reason"] == "chunk_timeout"


@_skip_no_fastapi
def test_boundary_chunk_timeout_classification(client_and_deps):
    """결함 2 회귀: ChunkTimeoutError가 chunk_timeout으로 분류 (hard_timeout 아님).

    'timeout' 문자열이 hard와 chunk 모두에 포함되더라도
    타입 매칭으로 chunk_timeout이 정확히 분류되는지 검증한다.
    """
    client, _, ChunkTimeoutError, *_ = client_and_deps

    def _raise(*args, **kwargs):
        raise ChunkTimeoutError("[chunk_timeout] chunk 3 exceeded 45s", _PARTIAL_PATH)

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", side_effect=_raise):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    cancelled = next(e for e in _parse_events(resp.text) if e.get("event") == "cancelled")
    assert cancelled["data"]["reason"] == "chunk_timeout", (
        f"chunk_timeout이 오분류됨: {cancelled['data']['reason']}"
    )


@_skip_no_fastapi
def test_boundary_hard_timeout_classification(client_and_deps):
    """결함 2 회귀: HardTimeoutError가 hard_timeout으로 정확히 분류된다."""
    client, _, _, HardTimeoutError, _ = client_and_deps

    def _raise(*args, **kwargs):
        raise HardTimeoutError("[hard_timeout] 180초 초과", _PARTIAL_PATH)

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", side_effect=_raise):
        resp = client.post("/api/analyze/stream", json=_STREAM_PAYLOAD)

    cancelled = next(e for e in _parse_events(resp.text) if e.get("event") == "cancelled")
    assert cancelled["data"]["reason"] == "hard_timeout"


# ─────────────── PR #675 회귀 테스트 (think-block 필터 + chunk flush) ──────────

@_skip_no_fastapi
def test_adv_think_block_tokens_not_in_chunk_events(client_and_deps):
    """think-block 필터 회귀: <think>...</think> 토큰이 chunk 이벤트에 포함되지 않는다.

    Qwen3 모델은 /no_think 지시에도 빈 thinking block(<think>\\n\\n</think>)을 emit한다.
    _think_state 상태 머신이 이 토큰들을 소비하고 chunk 이벤트에 누출하지 않는지 검증.
    """
    from butler_pc_core.inference.llm_runtime import LlmRuntime as _LR

    client, *_ = client_and_deps

    # Simulate Qwen3's null think block followed by real response tokens
    _think_tokens = ["<think>", "\n\n", "</think>", "실제", " 답변", " 입니다"]

    def _think_streaming_gen(self, prompt, cancel_event, max_tokens=512, temperature=0.2, stop=None):
        for tok in _think_tokens:
            if cancel_event.is_set():
                return
            yield tok

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None), \
         patch.object(_LR, "generate_stream_with_cancel", _think_streaming_gen):
        resp = client.post(
            "/api/analyze/stream",
            json={"file_path": "/tmp/f.txt", "total_chunks": 1, "output_dir": "/tmp"},
        )

    assert resp.status_code == 200
    events = _parse_events(resp.text)
    chunk_tokens = [e["data"]["token"] for e in events if e.get("event") == "chunk"]

    # think-block tokens must not appear in any chunk event
    for tok in ("<think>", "</think>"):
        assert not any(tok in t for t in chunk_tokens), (
            f"think 토큰 누출: '{tok}' in chunk_tokens={chunk_tokens}"
        )

    # Real response tokens must be present
    combined = "".join(chunk_tokens)
    assert "실제" in combined, f"실제 답변 토큰 없음: chunk_tokens={chunk_tokens}"


@_skip_no_fastapi
def test_adv_chunk_flush_each_token_separate_event(client_and_deps):
    """chunk flush 회귀: 각 토큰이 독립적인 chunk 이벤트로 전달된다.

    asyncio.sleep(0) 추가로 TCP flush가 보장되므로 토큰 수만큼 chunk 이벤트가 있어야 한다.
    """
    from butler_pc_core.inference.llm_runtime import LlmRuntime as _LR

    client, *_ = client_and_deps
    _tokens = ["첫째", " 둘째", " 셋째"]

    def _multi_token_gen(self, prompt, cancel_event, max_tokens=512, temperature=0.2, stop=None):
        for tok in _tokens:
            if cancel_event.is_set():
                return
            yield tok

    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None), \
         patch.object(_LR, "generate_stream_with_cancel", _multi_token_gen):
        resp = client.post(
            "/api/analyze/stream",
            json={"file_path": "/tmp/f.txt", "total_chunks": 1, "output_dir": "/tmp"},
        )

    events = _parse_events(resp.text)
    chunk_events = [e for e in events if e.get("event") == "chunk"]
    assert len(chunk_events) == len(_tokens), (
        f"chunk 이벤트 수 불일치: expected {len(_tokens)}, got {len(chunk_events)}"
    )
