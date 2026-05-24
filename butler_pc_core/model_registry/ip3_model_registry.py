from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .model_status import ModelStatusLevel, is_routing_executable


@dataclass(frozen=True)
class IP3ModelRegistration:
    model_id: str
    model_path: str
    sha256: str
    size_mib: int
    bpw: float
    model_status_level: str
    forward_verified: bool
    routing_executable: bool


BUTLER_1_7B_V4_RT = IP3ModelRegistration(
    model_id="butler-1.7b-v4-rt-q4_k_m",
    model_path="/Volumes/T7 Shield/학습모델/butler-1.7b-v4-rt/butler-1.7b-v4-rt-q4_k_m.gguf",
    sha256="60b9baee17696ca8e3a3aa0950a4d441ad3c4baa80bbd73ec9fa33c17cba0c1f",
    size_mib=1050,
    bpw=5.12,
    model_status_level=ModelStatusLevel.artifact_sealed.value,
    forward_verified=False,
    routing_executable=False,
)


def get_ip3_model_registry() -> dict[str, dict[str, object]]:
    return {BUTLER_1_7B_V4_RT.model_id: asdict(BUTLER_1_7B_V4_RT)}


def physical_model_probe(path: str | None = None) -> dict[str, object]:
    model_path = Path(path or BUTLER_1_7B_V4_RT.model_path)
    present = model_path.exists()
    return {
        "model_id": BUTLER_1_7B_V4_RT.model_id,
        "t7_model_file_present": present,
        "physical_model_sha_verified": False,
        "claim": "artifact_sealed_metadata_registered_only",
    }


def routing_allowed_for_registered_model() -> bool:
    return is_routing_executable(
        ModelStatusLevel(BUTLER_1_7B_V4_RT.model_status_level),
        BUTLER_1_7B_V4_RT.forward_verified,
        BUTLER_1_7B_V4_RT.routing_executable,
    )
