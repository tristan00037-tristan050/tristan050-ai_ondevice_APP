"""test_sidecar_routing_integration.py — Task Budget Router 사이드카 통합 테스트 (5 cases).

/api/analyze/stream 엔드포인트가 Router 결정을 SSE 이벤트로 올바르게 반영하는지 검증.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

try:
    from fastapi.testclient import TestClient
    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False

_skip = pytest.mark.skipif(not _FASTAPI_OK, reason="fastapi 미설치")


def _parse_events(raw: str) -> list[dict[str, Any]]:
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


def _get_client():
    import butler_sidecar as sidecar
    from butler_pc_core.inference.llm_runtime import LlmRuntime
    sidecar._SHARED_LLM = LlmRuntime(model_path=None)
    return TestClient(sidecar.app), sidecar


@pytest.fixture
def client_sidecar():
    client, sidecar = _get_client()
    yield client, sidecar


# ---------------------------------------------------------------------------

@_skip
def test_sidecar_emits_route_check_event(client_sidecar):
    """route_check meta 이벤트가 SSE 스트림 맨 앞에 발행된다."""
    client, _ = client_sidecar
    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None):
        resp = client.post(
            "/api/analyze/stream",
            data={"query": "안녕", "card_mode": "free", "total_chunks": "1", "output_dir": "/tmp"},
        )

    events = _parse_events(resp.text)
    # 첫 이벤트가 meta이며 route_check=True
    assert events, "이벤트 없음"
    first_meta = next((e for e in events if e.get("event") == "meta"), None)
    assert first_meta is not None
    assert first_meta["data"].get("route_check") is True
    assert "route" in first_meta["data"]


@_skip
def test_sidecar_team_hub_recommended_message(client_sidecar):
    """decide_task_budget가 TEAM_HUB_RECOMMENDED → complete에 허브 메시지 포함."""
    from butler_pc_core.router.task_budget_router import Route, TaskBudget

    client, _ = client_sidecar
    stub_budget = TaskBudget(
        file_bytes=500_000,
        estimated_tokens=100_000,
        page_count=0,
        route=Route.TEAM_HUB_RECOMMENDED,
        max_wall_time_sec=3,
        reason="test",
        user_message="이 자료는 팀 허브 PC에서 더 안정적으로 처리됩니다.",
    )
    with patch("butler_sidecar.decide_task_budget", return_value=stub_budget):
        resp = client.post(
            "/api/analyze/stream",
            data={"query": "대용량 파일", "total_chunks": "1", "output_dir": "/tmp"},
        )

    events = _parse_events(resp.text)
    event_types = [e["event"] for e in events]
    assert "complete" in event_types
    assert "error" not in event_types
    assert "phase_start" not in event_types  # LLM 파이프라인 미진입

    complete_ev = next(e for e in events if e["event"] == "complete")
    assert "팀 허브" in complete_ev["data"].get("result_text", "")


@_skip
def test_sidecar_refuse_with_team_hub_message(client_sidecar):
    """decide_task_budget가 REFUSE_TEAM_HUB → error 이벤트 발행."""
    from butler_pc_core.router.task_budget_router import Route, TaskBudget

    client, _ = client_sidecar
    stub_budget = TaskBudget(
        file_bytes=2 * 1024 * 1024,
        estimated_tokens=500_000,
        page_count=0,
        route=Route.REFUSE_TEAM_HUB,
        max_wall_time_sec=3,
        reason="test",
        user_message="이 자료는 PC Core 단독 처리 권장 범위를 초과합니다.",
    )
    with patch("butler_sidecar.decide_task_budget", return_value=stub_budget):
        resp = client.post(
            "/api/analyze/stream",
            data={"query": "초대용량", "total_chunks": "1", "output_dir": "/tmp"},
        )

    events = _parse_events(resp.text)
    error_ev = next((e for e in events if e["event"] == "error"), None)
    assert error_ev is not None
    assert error_ev["data"]["error_class"] == "input_too_large"
    assert "complete" not in [e["event"] for e in events]


@_skip
def test_sidecar_factpack_bypasses_router(client_sidecar):
    """텍스트 전용 쿼리 → route=PC_DIRECT → FactPack 경로 진입 가능."""
    client, _ = client_sidecar
    with patch("butler_sidecar.TimeoutController.check_hard_timeout", return_value=None):
        resp = client.post(
            "/api/analyze/stream",
            data={"query": "테스트 자유 질문", "total_chunks": "1", "output_dir": "/tmp"},
        )

    events = _parse_events(resp.text)
    # route_check 이벤트가 PC_DIRECT이어야 함 (파일 없음 → 0 bytes)
    route_ev = next(
        (e for e in events if e.get("event") == "meta" and e["data"].get("route_check")),
        None,
    )
    assert route_ev is not None
    assert route_ev["data"]["route"] == "pc_direct"
    # 전체 흐름에서 error가 없어야 함
    assert "error" not in [e["event"] for e in events]
    # complete 이벤트가 있어야 함
    assert "complete" in [e["event"] for e in events]


@_skip
def test_sidecar_pc_preview_with_partial_result(client_sidecar):
    """decide_task_budget가 PC_PREVIEW_TEAM_HUB → complete에 미리보기 메시지 + LLM 미진입."""
    from butler_pc_core.router.task_budget_router import Route, TaskBudget

    client, _ = client_sidecar
    preview_msg = "PC에서는 미리보기 요약만 제공합니다. 전체 분석은 팀 허브 연결 후 가능합니다."
    stub_budget = TaskBudget(
        file_bytes=400_000,
        estimated_tokens=80_000,
        page_count=0,
        route=Route.PC_PREVIEW_TEAM_HUB,
        max_wall_time_sec=30,
        reason="test",
        user_message=preview_msg,
    )
    with patch("butler_sidecar.decide_task_budget", return_value=stub_budget):
        resp = client.post(
            "/api/analyze/stream",
            data={"query": "중간 파일 미리보기", "total_chunks": "1", "output_dir": "/tmp"},
        )

    events = _parse_events(resp.text)
    event_types = [e["event"] for e in events]
    assert "complete" in event_types
    assert "phase_start" not in event_types  # LLM 파이프라인 미진입

    complete_ev = next(e for e in events if e["event"] == "complete")
    assert "미리보기" in complete_ev["data"].get("result_text", "")
