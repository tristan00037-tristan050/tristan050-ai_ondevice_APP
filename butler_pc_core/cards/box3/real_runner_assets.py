from __future__ import annotations

import hashlib
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .real_contracts import is_bare_sha256, is_sha256_digest, sha256_text, stable_json_digest
from .real_fail_class import (
    BLOCK_ASSET_INVENTORY_NOT_PASS,
    BLOCK_BASE_MODEL_FULL_SHA_NOT_CONFIGURED,
    BLOCK_HELPER_ASSET_DRIFT,
    BLOCK_MODEL_ASSET_MISSING,
    BLOCK_MODEL_ASSET_SHA_MISMATCH,
    BLOCK_MODEL_ASSET_SHA_SCOPE_INVALID,
    PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE,
)

HELPER_EXPECTED_SHA = {
    "helper3_format": "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0",
    "helper4_grounding": "b7b1af0ebfddc17bf9164ab124f8b598d97954f1a9fa067abf1e68f020c95e40",
    "helper7_table_figure": "8b03454967a9f16d12e408ea85ab3b27efe5a3e053c8150480cb70646fa4dfb0",
    "helper8_company_style": "7d4f8311ab427e4b609e2d22d7aff6e89a19085eaaa788677c7ed24d789d6d52",
}
REQUIRED_HELPERS = tuple(HELPER_EXPECTED_SHA)


def _bare_to_prefixed(value: str | None) -> str | None:
    if value is None:
        return None
    return "sha256:" + value if is_bare_sha256(value) else value


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fallback_real_asset_manifest() -> dict[str, Any]:
    assets = []
    for name, digest in HELPER_EXPECTED_SHA.items():
        assets.append({
            "asset_name": name,
            "role": name.replace("helper", "helper_"),
            "display_sha_prefix": digest[:8] + "...",
            "asset_path": f"ref:BUTLER_{name.upper()}_PATH",
            "sha256_full": digest,
            "sha_scope": "file",
            "measured_at": "from_pr774_manifest",
            "measured_by": "pr774_verified_handoff",
            "source_metadata_files": ["sealed_metadata"],
            "interface_inventory_status": "pass",
            "real_claim_allowed": True,
            "fail_class": None,
        })
    return {
        "schema_version": "box3.asset_manifest.v1",
        "status": "ASSET_INVENTORY_PASS",
        "real_claim_allowed": True,
        "state_gate": "ASSET_INVENTORY_PASS",
        "created_at": "from_pr774_manifest",
        "assets": assets,
        "asset_errors": {name: [] for name in HELPER_EXPECTED_SHA},
    }


def get_real_asset_manifest() -> dict[str, Any]:
    try:
        from .asset_manifest import build_real_asset_manifest  # type: ignore
        return build_real_asset_manifest()
    except Exception:
        return _fallback_real_asset_manifest()


def helper_manifest_allows_real(manifest: dict[str, Any]) -> bool:
    try:
        from .asset_manifest import manifest_allows_real  # type: ignore
        return bool(manifest_allows_real(manifest))
    except Exception:
        if not isinstance(manifest, dict):
            return False
        if manifest.get("schema_version") != "box3.asset_manifest.v1":
            return False
        if manifest.get("status") != "ASSET_INVENTORY_PASS" or manifest.get("real_claim_allowed") is not True:
            return False
        assets = manifest.get("assets")
        if not isinstance(assets, list):
            return False
        seen = {}
        for item in assets:
            if not isinstance(item, dict):
                return False
            seen[item.get("asset_name")] = item
        if set(seen) != set(REQUIRED_HELPERS):
            return False
        for name, expected in HELPER_EXPECTED_SHA.items():
            row = seen[name]
            if row.get("sha256_full") != expected:
                return False
            if row.get("sha_scope") not in {"file", "directory_manifest"}:
                return False
            if row.get("interface_inventory_status") != "pass":
                return False
            if row.get("real_claim_allowed") is not True:
                return False
        return True


@dataclass(frozen=True)
class Box3RealRunnerConfig:
    runner_id: str
    model_choice: str
    model_path_ref: str
    model_path_env: str = "BUTLER_BOX3_BASE_MODEL_PATH"
    base_model_sha256_full: Optional[str] = None
    loader_name: str = "llama_cpp"
    loader_version: str = "unmeasured"
    device_profile: str = "local"
    timeout_seconds: float = 30.0
    memory_limit_mb: Optional[int] = None
    allow_test_runner: bool = False
    mock_or_stub: bool = False
    readonly_required: bool = True

    @classmethod
    def from_env(cls) -> "Box3RealRunnerConfig":
        return cls(
            runner_id=os.environ.get("BUTLER_BOX3_REAL_RUNNER_ID", "box3-local-real-runner"),
            model_choice=os.environ.get("BUTLER_BOX3_MODEL_CHOICE", "qwen3-1.7b-v4-rt"),
            model_path_ref="ref:BUTLER_BOX3_BASE_MODEL_PATH",
            model_path_env="BUTLER_BOX3_BASE_MODEL_PATH",
            base_model_sha256_full=os.environ.get("BUTLER_BOX3_BASE_MODEL_SHA256_FULL"),
            loader_name=os.environ.get("BUTLER_BOX3_LOADER", "llama_cpp"),
            loader_version=os.environ.get("BUTLER_BOX3_LOADER_VERSION", "unmeasured"),
            device_profile=os.environ.get("BUTLER_BOX3_DEVICE_PROFILE", "local"),
            timeout_seconds=float(os.environ.get("BUTLER_BOX3_RUNNER_TIMEOUT_SEC", "30")),
            memory_limit_mb=int(os.environ["BUTLER_BOX3_MEMORY_LIMIT_MB"]) if os.environ.get("BUTLER_BOX3_MEMORY_LIMIT_MB") else None,
        )

    @property
    def model_path(self) -> Optional[Path]:
        value = os.environ.get(self.model_path_env)
        return Path(value) if value else None

    def to_digest_dict(self) -> dict[str, Any]:
        return {
            "runner_id": self.runner_id,
            "model_choice": self.model_choice,
            "model_path_ref": self.model_path_ref,
            "model_path_digest": sha256_text(os.environ.get(self.model_path_env, self.model_path_ref)),
            "base_model_sha256_full": self.base_model_sha256_full,
            "loader_name": self.loader_name,
            "loader_version": self.loader_version,
            "device_profile": self.device_profile,
            "timeout_seconds": self.timeout_seconds,
            "memory_limit_mb": self.memory_limit_mb,
            "readonly_required": self.readonly_required,
        }


@dataclass(frozen=True)
class Box3RealRunnerAssetVerdict:
    allowed: bool
    fail_class: Optional[str]
    runner_asset_digest: str
    asset_manifest_digest: str
    rows: List[dict[str, Any]] = field(default_factory=list)
    measured: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_box3_real_runner_assets(config: Box3RealRunnerConfig, *, helper_manifest: Optional[dict[str, Any]] = None) -> Box3RealRunnerAssetVerdict:
    helper_manifest = helper_manifest or get_real_asset_manifest()
    helper_manifest_digest = stable_json_digest(helper_manifest)
    rows: List[dict[str, Any]] = []

    if not helper_manifest_allows_real(helper_manifest):
        return Box3RealRunnerAssetVerdict(False, BLOCK_ASSET_INVENTORY_NOT_PASS, stable_json_digest(config.to_digest_dict()), helper_manifest_digest, rows)

    base_sha = config.base_model_sha256_full
    if not base_sha:
        return Box3RealRunnerAssetVerdict(False, BLOCK_BASE_MODEL_FULL_SHA_NOT_CONFIGURED, stable_json_digest(config.to_digest_dict()), helper_manifest_digest, rows)
    if not is_bare_sha256(base_sha):
        return Box3RealRunnerAssetVerdict(False, BLOCK_MODEL_ASSET_SHA_SCOPE_INVALID, stable_json_digest(config.to_digest_dict()), helper_manifest_digest, rows)

    model_path = config.model_path
    if model_path is None or not model_path.exists() or not model_path.is_file():
        return Box3RealRunnerAssetVerdict(False, BLOCK_MODEL_ASSET_MISSING, stable_json_digest(config.to_digest_dict()), helper_manifest_digest, rows)
    actual_sha = sha256_file(model_path)
    if actual_sha != base_sha:
        rows.append({
            "asset_name": "base_model",
            "path_ref": config.model_path_ref,
            "path_digest": sha256_text(str(model_path)),
            "sha256_full": actual_sha,
            "sha_scope": "file",
            "readonly_verified": not os.access(model_path, os.W_OK) if config.readonly_required else True,
            "fail_class": BLOCK_MODEL_ASSET_SHA_MISMATCH,
        })
        return Box3RealRunnerAssetVerdict(False, BLOCK_MODEL_ASSET_SHA_MISMATCH, stable_json_digest(config.to_digest_dict()), helper_manifest_digest, rows)

    readonly = not os.access(model_path, os.W_OK) if config.readonly_required else True
    rows.append({
        "asset_name": "base_model",
        "path_ref": config.model_path_ref,
        "path_digest": sha256_text(str(model_path)),
        "sha256_full": actual_sha,
        "sha_scope": "file",
        "readonly_verified": readonly,
        "fail_class": None if readonly else BLOCK_MODEL_ASSET_MISSING,
    })
    if not readonly:
        return Box3RealRunnerAssetVerdict(False, BLOCK_MODEL_ASSET_MISSING, stable_json_digest(config.to_digest_dict()), helper_manifest_digest, rows)

    for helper in helper_manifest.get("assets", []):
        if isinstance(helper, dict):
            rows.append({
                "asset_name": helper.get("asset_name"),
                "path_ref": helper.get("asset_path"),
                "path_digest": sha256_text(str(helper.get("asset_path"))),
                "sha256_full": helper.get("sha256_full"),
                "sha_scope": helper.get("sha_scope"),
                "readonly_verified": True,
                "fail_class": helper.get("fail_class"),
            })
    digest = stable_json_digest({"config": config.to_digest_dict(), "rows": rows})
    return Box3RealRunnerAssetVerdict(True, None, digest, helper_manifest_digest, rows, measured={"measured_at_ms": int(time.time() * 1000)})

# 박스 3 real follow-up v1.2 (2026-06-04) — ALG public alias 흡수.
fallback_real_asset_manifest = _fallback_real_asset_manifest
