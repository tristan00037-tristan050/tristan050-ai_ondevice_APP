from __future__ import annotations

from enum import Enum


class ModelStatusLevel(str, Enum):
    artifact_sealed = "artifact_sealed"
    forward_verified = "forward_verified"
    pipeline_verified = "pipeline_verified"
    runtime_live = "runtime_live"
    blocked = "blocked"


# Routing 본질이 허용되는 ModelStatusLevel 본질 allowlist (fail-closed 정책).
# deny by default: 본 set 본질에 없는 모든 status는 routing 거부.
# Codex P1 정정 (2026-05-23): denylist (level != artifact_sealed) 본질을
# allowlist로 전환 — blocked 본질 모델이 stale flags로 routing 허용되던 본질 차단.
ROUTING_EXECUTABLE_STATUS_ALLOWLIST: frozenset[ModelStatusLevel] = frozenset({
    ModelStatusLevel.pipeline_verified,
    ModelStatusLevel.runtime_live,
})


def is_routing_executable(level: ModelStatusLevel, forward_verified: bool, routing_executable: bool) -> bool:
    """
    Routing 가능 여부 본질 판정 (fail-closed allowlist 정책).

    조건 본질 3중 (AND):
    - level 본질이 ROUTING_EXECUTABLE_STATUS_ALLOWLIST에 포함
    - forward_verified True
    - routing_executable True

    blocked / artifact_sealed / forward_verified / 기타 본질 status는 모두 거부 본질.
    stale flags 본질이 잔존해도 status 본질이 allowlist 외이면 거부.
    """
    return (
        level in ROUTING_EXECUTABLE_STATUS_ALLOWLIST
        and forward_verified
        and routing_executable
    )
