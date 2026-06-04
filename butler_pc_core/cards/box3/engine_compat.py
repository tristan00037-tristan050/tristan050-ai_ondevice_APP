from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .actual_fail_class import PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE

ModelFormat = Literal["GGUF", "MLX", "unknown"]
EngineName = Literal["llama_cpp", "mlx_lm", "none"]


@dataclass(frozen=True)
class EngineCompatibilityVerdict:
    model_format: ModelFormat
    required_engine: EngineName
    import_available: bool
    compatible: bool
    fail_class: str | None
    detail_code: str

    def to_dict(self) -> dict:
        return asdict(self)


def detect_model_format(path_ref_or_name: str | None) -> ModelFormat:
    value = (path_ref_or_name or "").lower()
    if value.endswith(".gguf") or "gguf" in value:
        return "GGUF"
    if "mlx" in value or value.endswith(".safetensors") or value.endswith(".npz"):
        # MLX models are directories in practice; this keeps the dispatcher conservative.
        return "MLX"
    return "unknown"


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def check_engine_model_compatibility(model_format: ModelFormat) -> EngineCompatibilityVerdict:
    if model_format == "GGUF":
        available = _module_available("llama_cpp")
        return EngineCompatibilityVerdict(
            model_format=model_format,
            required_engine="llama_cpp",
            import_available=available,
            compatible=available,
            fail_class=None if available else PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
            detail_code="GGUF_REQUIRES_LLAMA_CPP",
        )
    if model_format == "MLX":
        available = _module_available("mlx_lm") and _module_available("mlx")
        return EngineCompatibilityVerdict(
            model_format=model_format,
            required_engine="mlx_lm",
            import_available=available,
            compatible=available,
            fail_class=None if available else PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
            detail_code="MLX_REQUIRES_MLX_AND_MLX_LM",
        )
    return EngineCompatibilityVerdict(
        model_format="unknown",
        required_engine="none",
        import_available=False,
        compatible=False,
        fail_class=PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
        detail_code="UNKNOWN_MODEL_FORMAT",
    )
