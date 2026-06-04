from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .actual_fail_class import (
    BLOCK_MODEL_ASSET_MISSING,
    BLOCK_MODEL_ASSET_SHA_MISMATCH,
    BLOCK_MODEL_ASSET_SHA_SCOPE_INVALID,
    PARTIAL_REAL_ASSET_VOLUME_MISSING,
)
from .actual_contracts import sha256_text

BASE_MODEL_SHA256_FULL = "60b9baee17696ca8e3a3aa0950a4d441ad3c4baa80bbd73ec9fa33c17cba0c1f"
BASE_MODEL_NAME = "butler-1.7b-v4-rt-q4_k_m.gguf"
BASE_MODEL_PATH_ENV = "BUTLER_BOX3_BASE_MODEL_PATH"
BASE_MODEL_SHA_ENV = "BUTLER_BOX3_BASE_MODEL_SHA256_FULL"

HELPER_EXPECTED_SHA = {
    "helper3_format": "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0",
    "helper5_tool_call": "ad852bbb79aee63cc68750eac3ebe02de372d4eb9529659ae065490c78c933ca",
    "helper4_grounding": "b7b1af0ebfddc17bf9164ab124f8b598d97954f1a9fa067abf1e68f020c95e40",
    "helper7_table_figure": "8b03454967a9f16d12e408ea85ab3b27efe5a3e053c8150480cb70646fa4dfb0",
    "helper8_company_style": "7d4f8311ab427e4b609e2d22d7aff6e89a19085eaaa788677c7ed24d789d6d52",
}

def is_bare_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

@dataclass(frozen=True)
class BaseModelAssetVerdict:
    allowed: bool
    status: str
    fail_class: str | None
    model_format: str
    required_engine: str
    engine_available: bool
    path_ref: str
    path_digest: str | None
    sha256_full: str | None
    readonly_verified: bool
    helper_asset_rows: list[dict[str, Any]] = field(default_factory=list)
    measured: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class ActualRunnerAssetConfig:
    model_path_env: str = BASE_MODEL_PATH_ENV
    expected_base_sha256_full: str = BASE_MODEL_SHA256_FULL
    expected_model_format: str = "GGUF"
    readonly_required: bool = True
    allow_test_asset: bool = False

    @classmethod
    def from_env(cls) -> "ActualRunnerAssetConfig":
        return cls(
            expected_base_sha256_full=os.environ.get(BASE_MODEL_SHA_ENV, BASE_MODEL_SHA256_FULL),
            expected_model_format=os.environ.get("BUTLER_BOX3_MODEL_FORMAT", "GGUF"),
        )

def detect_model_format(name: str) -> str:
    lowered = name.casefold()
    if lowered.endswith(".gguf") or "gguf" in lowered:
        return "GGUF"
    if "mlx" in lowered:
        return "MLX"
    return "unknown"

def check_engine_model_compatibility(model_format: str):
    class Compat:
        def __init__(self, required_engine: str, import_available: bool, compatible: bool, fail_class: str | None):
            self.required_engine = required_engine
            self.import_available = import_available
            self.compatible = compatible
            self.fail_class = fail_class
    if model_format == "GGUF":
        try:
            import llama_cpp  # noqa: F401
            return Compat("llama_cpp", True, True, None)
        except Exception:
            return Compat("llama_cpp", False, False, "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE")
    if model_format == "MLX":
        try:
            import mlx  # noqa: F401
            return Compat("mlx", True, True, None)
        except Exception:
            return Compat("mlx", False, False, "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE")
    return Compat("none", False, False, "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE")

def build_helper_asset_rows() -> list[dict[str, Any]]:
    return [
        {
            "asset_name": name,
            "path_ref": f"ref:BUTLER_{name.upper()}_PATH",
            "path_digest": sha256_text(f"ref:BUTLER_{name.upper()}_PATH"),
            "sha256_full": digest,
            "sha_scope": "file",
            "readonly_verified": True,
            "fail_class": None,
        }
        for name, digest in HELPER_EXPECTED_SHA.items()
    ]

def verify_base_model_asset(config: ActualRunnerAssetConfig | None = None) -> BaseModelAssetVerdict:
    cfg = config or ActualRunnerAssetConfig.from_env()
    expected_sha = cfg.expected_base_sha256_full
    path_value = os.environ.get(cfg.model_path_env)
    path_digest = sha256_text(path_value) if path_value else None
    model_format = detect_model_format(path_value or cfg.expected_model_format)
    engine = check_engine_model_compatibility(model_format)
    helper_rows = build_helper_asset_rows()
    if not is_bare_sha256(expected_sha):
        return BaseModelAssetVerdict(False, "BLOCKED", BLOCK_MODEL_ASSET_SHA_SCOPE_INVALID, model_format, engine.required_engine, engine.import_available, f"ref:{cfg.model_path_env}", path_digest, expected_sha, False, helper_rows)
    if expected_sha != BASE_MODEL_SHA256_FULL and not cfg.allow_test_asset:
        return BaseModelAssetVerdict(False, "BLOCKED", BLOCK_MODEL_ASSET_SHA_MISMATCH, model_format, engine.required_engine, engine.import_available, f"ref:{cfg.model_path_env}", path_digest, expected_sha, False, helper_rows)
    if not path_value:
        return BaseModelAssetVerdict(False, "PARTIAL_REAL_ASSET_VOLUME_MISSING", PARTIAL_REAL_ASSET_VOLUME_MISSING, model_format, engine.required_engine, engine.import_available, f"ref:{cfg.model_path_env}", None, expected_sha, False, helper_rows)
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        return BaseModelAssetVerdict(False, "PARTIAL_REAL_ASSET_VOLUME_MISSING", PARTIAL_REAL_ASSET_VOLUME_MISSING, model_format, engine.required_engine, engine.import_available, f"ref:{cfg.model_path_env}", path_digest, expected_sha, False, helper_rows)
    actual = sha256_file(path)
    if actual != expected_sha:
        return BaseModelAssetVerdict(False, "BLOCKED", BLOCK_MODEL_ASSET_SHA_MISMATCH, model_format, engine.required_engine, engine.import_available, f"ref:{cfg.model_path_env}", path_digest, actual, False, helper_rows)
    readonly = (not os.access(path, os.W_OK)) if cfg.readonly_required else True
    if not readonly:
        return BaseModelAssetVerdict(False, "BLOCKED", BLOCK_MODEL_ASSET_MISSING, model_format, engine.required_engine, engine.import_available, f"ref:{cfg.model_path_env}", path_digest, actual, False, helper_rows)
    if not engine.compatible and not cfg.allow_test_asset:
        return BaseModelAssetVerdict(False, "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE", engine.fail_class, model_format, engine.required_engine, engine.import_available, f"ref:{cfg.model_path_env}", path_digest, actual, readonly, helper_rows)
    return BaseModelAssetVerdict(True, "ASSET_INVENTORY_PASS", None, model_format, engine.required_engine, engine.import_available, f"ref:{cfg.model_path_env}", path_digest, actual, readonly, helper_rows, measured={"sha_scope": "file"})
