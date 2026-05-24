"""
ModelStatusLevel routing 본질 회귀 방지 테스트.

Codex P1 정정 (2026-05-23, PR #752):
- denylist (level != artifact_sealed) → allowlist 본질 전환
- blocked 본질 모델이 stale flags 본질로 routing 허용되던 결함 본질 차단
- fail-closed 정책 본질 (deny by default)
"""
import pytest

from butler_pc_core.model_registry.model_status import (
    ModelStatusLevel,
    ROUTING_EXECUTABLE_STATUS_ALLOWLIST,
    is_routing_executable,
)


# ──────────────────────────────────────────────────────────────────────────────
# 허용 본질 — allowlist 본질 status + 모든 flag 본질 True
# ──────────────────────────────────────────────────────────────────────────────

def test_pipeline_verified_with_all_flags_routes():
    """pipeline_verified 본질 + flags True 본질 → routing 허용."""
    assert is_routing_executable(
        ModelStatusLevel.pipeline_verified, True, True
    ) is True


def test_runtime_live_with_all_flags_routes():
    """runtime_live 본질 + flags True 본질 → routing 허용."""
    assert is_routing_executable(
        ModelStatusLevel.runtime_live, True, True
    ) is True


# ──────────────────────────────────────────────────────────────────────────────
# 거부 본질 — Codex 결함 핵심 본질 (blocked + stale flags 본질이 routing되던 본질)
# ──────────────────────────────────────────────────────────────────────────────

def test_blocked_with_stale_true_flags_denied():
    """
    Codex 결함의 핵심 본질 — blocked 본질 + flags 잔존 True 본질 → routing 거부.
    이 본질이 PASS여야 결함 정정 본질이 정합.
    """
    assert is_routing_executable(
        ModelStatusLevel.blocked, True, True
    ) is False, "blocked 본질이 stale flags로 routing 허용됨 — 결함 잔존"


def test_artifact_sealed_with_all_flags_denied():
    """artifact_sealed 본질은 routing 거부 (기존 본질 보존)."""
    assert is_routing_executable(
        ModelStatusLevel.artifact_sealed, True, True
    ) is False


# ──────────────────────────────────────────────────────────────────────────────
# flag 본질 검증 — allowlisted status 본질이어도 flag False면 거부
# ──────────────────────────────────────────────────────────────────────────────

def test_pipeline_verified_without_forward_verified_denied():
    """allowlisted status 본질이어도 forward_verified=False 본질이면 거부."""
    assert is_routing_executable(
        ModelStatusLevel.pipeline_verified, False, True
    ) is False


def test_pipeline_verified_without_routing_executable_denied():
    """allowlisted status 본질이어도 routing_executable=False 본질이면 거부."""
    assert is_routing_executable(
        ModelStatusLevel.pipeline_verified, True, False
    ) is False


# ──────────────────────────────────────────────────────────────────────────────
# allowlist 본질 자체 정합 검증
# ──────────────────────────────────────────────────────────────────────────────

def test_allowlist_is_immutable_frozenset():
    """allowlist 본질이 frozenset 본질이어서 런타임 수정 0."""
    assert isinstance(ROUTING_EXECUTABLE_STATUS_ALLOWLIST, frozenset)
    with pytest.raises(AttributeError):
        ROUTING_EXECUTABLE_STATUS_ALLOWLIST.add(ModelStatusLevel.blocked)  # type: ignore[attr-defined]
