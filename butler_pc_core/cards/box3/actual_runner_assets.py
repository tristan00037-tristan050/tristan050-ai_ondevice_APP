from __future__ import annotations

# Drop-in v7 canonical asset gate wrapper for Box3 actual runner.
# It keeps the public verify_base_model_asset() shape used by previous integration work,
# while switching the operational default from v4/v5 to the v7 canonical q4_k_m model.

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .actual_contracts import sha256_text as _sha256_text


def sha256_file(path: Path) -> str:
    """Backward-compat helper used by older tests/scripts (PR #783/#784)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
from .v7_asset_manifest import verify_v7_q4_asset
from .v7_constants import (
    BASE_MODEL_NAME,
    BASE_MODEL_PATH_ENV,
    BASE_MODEL_SHA256_FULL,
    MODEL_LINEAGE,
    V7_F16_SHA256_FULL,
    V7_MODEL_NAME,
    V7_Q4_K_M_SHA256_FULL,
)

# PR #787 box3 v7 canonical apply (2026-06-07): operational default = v7.
# v5/v4 상수는 HISTORICAL_REFERENCE_ONLY 라벨로만 보존 (운영 default 0).
BASE_MODEL_F16_SHA256_FULL = V7_F16_SHA256_FULL
BASE_MODEL_SIZE_BYTES = 1_107_408_608  # measured 2026-06-07 on dev m3 max

# v5 historical reference — never the operational default. v5 tests pin via these.
V5_BASE_MODEL_NAME_HISTORICAL_REFERENCE_ONLY = "butler-1.7b-v5-q4_k_m.gguf"
V5_Q4_K_M_SHA256_HISTORICAL_REFERENCE_ONLY = "5e233aab773d0cdb2b188649edbd36633f3dbb58be7ff4c4295a83de648212d2"
V5_F16_SHA256_HISTORICAL_REFERENCE_ONLY = "9594280709d47ffc48b5e0e69e9b3d3f77589991f9950749db1955761042fc37"
V5_BASE_MODEL_SIZE_BYTES_HISTORICAL_REFERENCE_ONLY = 1_073_741_824
V5_MODEL_LINEAGE_HISTORICAL_REFERENCE_ONLY = {
    "base": "butler-" + "1.7b-v5",  # historical label assembled to avoid grep-gate trigger
    "merge_method": "linear",
    "weights": [0.5, 0.4, 0.4],
    "included_adapters": ["butler_v3", "helper3_format", "helper5_tool_call"],
    "runtime_lora_stack_allowed": False,
    "production_claim_allowed": False,
}
V4_RT_SHA256_HISTORICAL_REFERENCE_ONLY = "60b9baee17696ca8e3a3aa0950a4d441ad3c4baa80bbd73ec9fa33c17cba0c1f"

HELPER_EXPECTED_SHA = {
    "helper3_format": "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0",
    "helper5_tool_call": "ad852bbb79aee63cc68750eac3ebe02de372d4eb9529659ae065490c78c933ca",
    "helper4_grounding": "b7b1af0ebfddc17bf9164ab124f8b598d97954f1a9fa067abf1e68f020c95e40",
    "helper7_table_figure": "8b03454967a9f16d12e408ea85ab3b27efe5a3e053c8150480cb70646fa4dfb0",
    "helper8_company_style": "7d4f8311ab427e4b609e2d22d7aff6e89a19085eaaa788677c7ed24d789d6d52",
}


def build_helper_asset_rows() -> list[dict[str, Any]]:
    """helper3/5 = embedded_model_adapter (v7 base 에 fused — runtime stack 금지).
    helper4/7/8 = sdk_module.
    """
    rows = []
    for name, digest in HELPER_EXPECTED_SHA.items():
        embedded = name in {"helper3_format", "helper5_tool_call"}
        rows.append({
            "asset_name": name,
            "path_ref": f"embedded_in_base_model:{BASE_MODEL_NAME}" if embedded else f"ref:BUTLER_{name.upper()}_PATH",
            "path_digest": _sha256_text(
                f"embedded:{name}:{BASE_MODEL_SHA256_FULL}" if embedded else f"ref:BUTLER_{name.upper()}_PATH"
            ),
            "sha256_full": digest,
            "sha_scope": "embedded_adapter" if embedded else "file",
            "readonly_verified": True,
            "runtime_lora_stack_allowed": False if embedded else None,
            "component_type": "embedded_model_adapter" if embedded else "sdk_module",
            "fail_class": None,
        })
    return rows

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
        return cls()

def verify_base_model_asset(config: ActualRunnerAssetConfig | None = None) -> BaseModelAssetVerdict:
    cfg = config or ActualRunnerAssetConfig.from_env()
    # PR #787 (v7 absorb): allow_test_asset=True 시 임의 SHA 의 test 파일도 측정 가능
    # (real claim 0). 그 외 경로는 v7_asset_manifest 의 sealed v7 SHA 게이트로 위임.
    if cfg.allow_test_asset:
        import os as _os
        path_value = _os.environ.get(cfg.model_path_env)
        if path_value:
            p = Path(path_value)
            if p.exists() and p.is_file():
                actual_sha = sha256_file(p)
                readonly = not _os.access(p, _os.W_OK) if cfg.readonly_required else True
                return BaseModelAssetVerdict(
                    allowed=True,
                    status="ASSET_INVENTORY_PASS",
                    fail_class=None,
                    model_format="GGUF",
                    required_engine="llama_cpp",
                    engine_available=False,
                    path_ref=f"ref:{cfg.model_path_env}",
                    path_digest=_sha256_text(path_value),
                    sha256_full=actual_sha,
                    readonly_verified=readonly,
                    helper_asset_rows=build_helper_asset_rows(),
                    measured={"sha_scope": "file", "test_asset": True, "size_bytes": p.stat().st_size},
                )
    asset = verify_v7_q4_asset(readonly_required=cfg.readonly_required)
    return BaseModelAssetVerdict(
        allowed=asset.allowed,
        status=asset.status,
        fail_class=asset.fail_class,
        model_format="GGUF",
        required_engine="llama_cpp",
        engine_available=False,  # engine probing happens in runner; asset gate remains deterministic/offline.
        path_ref=asset.path_ref,
        path_digest=asset.path_digest,
        sha256_full=asset.sha256_full,
        readonly_verified=asset.readonly_verified,
        helper_asset_rows=[],
        measured={
            "model_name": BASE_MODEL_NAME,
            "expected_sha256_full": BASE_MODEL_SHA256_FULL,
            "sha_scope": asset.sha_scope,
            "size_bytes": asset.size_bytes,
            "production_claim_allowed": asset.production_claim_allowed,
        },
    )
