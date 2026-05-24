from __future__ import annotations

from enum import Enum


class ModelStatusLevel(str, Enum):
    artifact_sealed = "artifact_sealed"
    forward_verified = "forward_verified"
    pipeline_verified = "pipeline_verified"
    runtime_live = "runtime_live"
    blocked = "blocked"


def is_routing_executable(level: ModelStatusLevel, forward_verified: bool, routing_executable: bool) -> bool:
    return bool(level != ModelStatusLevel.artifact_sealed and forward_verified and routing_executable)
