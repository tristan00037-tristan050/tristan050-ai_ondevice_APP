from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

MODEL_STATUS_LEVELS = ("artifact_sealed", "forward_verified", "pipeline_verified", "runtime_live", "blocked")

@dataclass(frozen=True)
class ModelStatus:
    model_id: str
    status: str
    hidden_size: int | None = None
    artifact_digest: str | None = None
    logits_digest: str | None = None
    forward_verified: bool = False
    pipeline_verified: bool = False
    runtime_live: bool = False
    allowed_for_sensitive_data: bool = False

    def __post_init__(self) -> None:
        if self.status not in MODEL_STATUS_LEVELS:
            raise ValueError(f"invalid model status: {self.status}")

    @property
    def routing_executable(self) -> bool:
        return self.status in {"forward_verified", "pipeline_verified", "runtime_live"} and self.forward_verified is True


def default_model_registry() -> Dict[str, ModelStatus]:
    # IP1 v5.3r is artifact_sealed only; v5.4 evidence is required before executable local_1_7b routing.
    return {
        "local_1_7b": ModelStatus(model_id="local_1_7b", status="artifact_sealed", hidden_size=2048, forward_verified=False, allowed_for_sensitive_data=True),
        "local_4b": ModelStatus(model_id="local_4b", status="blocked", hidden_size=None, forward_verified=False),
        "central_server": ModelStatus(model_id="central_server", status="runtime_live", forward_verified=True, runtime_live=True, allowed_for_sensitive_data=False),
        "external_api": ModelStatus(model_id="external_api", status="runtime_live", forward_verified=True, runtime_live=True, allowed_for_sensitive_data=False),
    }


def registry_from_ip1_status(forward_verified: bool, logits_digest: str | None = None) -> Dict[str, ModelStatus]:
    status = "forward_verified" if forward_verified else "artifact_sealed"
    return {
        **default_model_registry(),
        "local_1_7b": ModelStatus(
            model_id="local_1_7b",
            status=status,
            hidden_size=2048,
            logits_digest=logits_digest,
            forward_verified=forward_verified,
            allowed_for_sensitive_data=True,
        ),
    }
