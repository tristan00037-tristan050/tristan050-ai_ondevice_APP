"""test_task_budget_router.py — Task Budget Router 단위 테스트 (D-1-A).

decide_task_budget() 의 Route 결정 + TaskBudget 필드 검증 (10 cases).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from butler_pc_core.router.task_budget_router import (
    Route,
    TaskBudget,
    decide_task_budget,
)

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
KB = 1024
MB = 1024 * 1024


# ---------------------------------------------------------------------------
# 테스트 케이스
# ---------------------------------------------------------------------------

def test_route_50kb_direct():
    """50 KB 이하 파일 → PC_DIRECT, max_wall_time=60."""
    budget = decide_task_budget(file_bytes=40 * KB, estimated_tokens=4_000)
    assert budget.route == Route.PC_DIRECT
    assert budget.max_wall_time_sec == 60
    assert budget.file_bytes == 40 * KB


def test_route_150kb_chunked():
    """50 KB 초과 ~ 200 KB 이하 파일 → PC_CHUNKED, max_wall_time=180."""
    budget = decide_task_budget(file_bytes=150 * KB, estimated_tokens=30_000)
    assert budget.route == Route.PC_CHUNKED
    assert budget.max_wall_time_sec == 180


def test_route_500kb_hub_recommended_when_paired():
    """500 KB 파일 + hub_paired=True → TEAM_HUB_RECOMMENDED."""
    budget = decide_task_budget(file_bytes=500 * KB, estimated_tokens=100_000, hub_paired=True)
    assert budget.route == Route.TEAM_HUB_RECOMMENDED
    assert budget.max_wall_time_sec == 3


def test_route_500kb_preview_when_not_paired():
    """500 KB 파일 + hub_paired=False (기본) → PC_PREVIEW_TEAM_HUB."""
    budget = decide_task_budget(file_bytes=500 * KB, estimated_tokens=100_000, hub_paired=False)
    assert budget.route == Route.PC_PREVIEW_TEAM_HUB
    assert budget.max_wall_time_sec == 30


def test_route_2mb_refused():
    """2 MB 초과 파일 → REFUSE_TEAM_HUB, hub_paired 무관."""
    for paired in (True, False):
        budget = decide_task_budget(file_bytes=2 * MB, estimated_tokens=500_000, hub_paired=paired)
        assert budget.route == Route.REFUSE_TEAM_HUB
        assert budget.max_wall_time_sec == 3


def test_route_high_token_count():
    """8K 토큰 이하 → PC_DIRECT (파일 크기와 무관)."""
    budget = decide_task_budget(file_bytes=60 * KB, estimated_tokens=7_999)
    assert budget.route == Route.PC_DIRECT


def test_route_high_page_count():
    """15 페이지 이하 → PC_CHUNKED (파일이 200 KB를 초과해도)."""
    budget = decide_task_budget(
        file_bytes=180 * KB,
        estimated_tokens=40_000,
        page_count=10,
    )
    assert budget.route == Route.PC_CHUNKED


def test_route_factpack_question_always_pc_direct():
    """텍스트 전용 쿼리 (파일 0 bytes, 토큰 0) → PC_DIRECT (FactPack 경로 보호)."""
    budget = decide_task_budget(file_bytes=0, estimated_tokens=0)
    assert budget.route == Route.PC_DIRECT
    assert budget.max_wall_time_sec == 60


def test_route_user_message_localized_korean():
    """모든 Route에 한국어 user_message가 존재한다."""
    cases = [
        decide_task_budget(file_bytes=0, estimated_tokens=0),
        decide_task_budget(file_bytes=150 * KB, estimated_tokens=30_000),
        decide_task_budget(file_bytes=500 * KB, estimated_tokens=100_000, hub_paired=True),
        decide_task_budget(file_bytes=500 * KB, estimated_tokens=100_000, hub_paired=False),
        decide_task_budget(file_bytes=2 * MB, estimated_tokens=500_000),
    ]
    for budget in cases:
        assert isinstance(budget.user_message, str)
        assert len(budget.user_message) > 0
        # 한글 포함 확인 (유니코드 가나다 범위)
        assert any("가" <= ch <= "힣" for ch in budget.user_message), (
            f"user_message에 한글 없음: '{budget.user_message}' (route={budget.route})"
        )


def test_route_max_wall_time_consistent():
    """각 Route의 max_wall_time_sec이 사양서 정의와 일치한다."""
    expected = {
        Route.PC_DIRECT: 60,
        Route.PC_CHUNKED: 180,
        Route.TEAM_HUB_RECOMMENDED: 3,
        Route.PC_PREVIEW_TEAM_HUB: 30,
        Route.REFUSE_TEAM_HUB: 3,
    }
    results = {
        Route.PC_DIRECT: decide_task_budget(0, 0),
        Route.PC_CHUNKED: decide_task_budget(150 * KB, 30_000),
        Route.TEAM_HUB_RECOMMENDED: decide_task_budget(500 * KB, 100_000, hub_paired=True),
        Route.PC_PREVIEW_TEAM_HUB: decide_task_budget(500 * KB, 100_000, hub_paired=False),
        Route.REFUSE_TEAM_HUB: decide_task_budget(2 * MB, 500_000),
    }
    for route, budget in results.items():
        assert budget.max_wall_time_sec == expected[route], (
            f"{route}: expected {expected[route]}s got {budget.max_wall_time_sec}s"
        )
