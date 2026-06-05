from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

V5_MODEL_NAME = "butler-1.7b-v5-q4_k_m.gguf"
V5_Q4_K_M_SHA256_FULL = "5e233aab773d0cdb2b188649edbd36633f3dbb58be7ff4c4295a83de648212d2"
V5_F16_SHA256_FULL = "9594280709d47ffc48b5e0e69e9b3d3f77589991f9950749db1955761042fc37"
V5_SCHEMA_VERSION = "box3.v5_asset_manifest.v1_2"
V5_ENV_PATH = "BUTLER_BOX3_BASE_MODEL_PATH"
V5_ENV_SHA = "BUTLER_BOX3_BASE_MODEL_SHA256_FULL"
V4_FORBIDDEN_NAME_FRAGMENTS = ("v4-rt", "v4_rt", "butler-1.7b-v4", "butler-1.7b-v4-rt-q4_k_m.gguf")
FULL_SHA_RE = re.compile(r"^[a-f0-9]{64}$")

MODEL_LINEAGE = {
    "base": "butler-1.7b-v5",
    "merge_method": "linear",
    "weights": [0.5, 0.4, 0.4],
    "included_adapters": ["butler_v3", "helper3_format", "helper5_tool_call"],
    "runtime_lora_stack_allowed": False,
    "production_claim_allowed": False,
}

@dataclass(frozen=True)
class V5AssetRecord:
    asset_name: str
    role: str
    path_ref: str
    path_digest: str | None
    sha256_full: str | None
    sha_scope: Literal["file", "directory_manifest", "unknown"]
    size_bytes: int | None
    readonly_verified: bool
    measured_at: str | None
    fail_class: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class V5AssetManifest:
    schema_version: str
    status: str
    model_choice: str
    model_lineage: dict[str, Any]
    asset: V5AssetRecord
    v4_default_reference_zero: bool
    raw_saved_zero: bool = True
    external_send_zero: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        _assert_digest_only_manifest(payload)
        return payload

def is_full_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(FULL_SHA_RE.fullmatch(value))

def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _path_has_v4_reference(path_text: str | None) -> bool:
    if not path_text:
        return False
    lower = path_text.casefold()
    return any(fragment in lower for fragment in V4_FORBIDDEN_NAME_FRAGMENTS)

def _assert_digest_only_manifest(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    forbidden = ("/Users/", "/home/", "/Volumes/", "sk-proj-", "BEGIN PRIVATE KEY")
    for item in forbidden:
        if item in encoded:
            raise AssertionError(f"raw/path/secret leaked into v5 manifest: {item}")

def build_v5_asset_manifest(model_path: Path | None = None, *, readonly_required: bool = True) -> V5AssetManifest:
    env_path = os.environ.get(V5_ENV_PATH)
    selected = model_path or (Path(env_path) if env_path else None)
    expected_sha = os.environ.get(V5_ENV_SHA, V5_Q4_K_M_SHA256_FULL)

    path_ref = f"ref:{V5_ENV_PATH}"
    if not is_full_sha256(expected_sha) or expected_sha != V5_Q4_K_M_SHA256_FULL:
        asset = V5AssetRecord(
            "box3_v5_base_model", "base_model", path_ref,
            sha256_text(str(selected or path_ref)), expected_sha,
            "file" if is_full_sha256(expected_sha) else "unknown", None, False, None,
            "BLOCK_MODEL_ASSET_SHA_MISMATCH" if is_full_sha256(expected_sha) else "BLOCK_MODEL_ASSET_SHA_SCOPE_INVALID",
        )
        return V5AssetManifest(V5_SCHEMA_VERSION, "BLOCKED", V5_MODEL_NAME, MODEL_LINEAGE, asset, not _path_has_v4_reference(str(selected or "")))

    if selected is None or not selected.exists() or not selected.is_file():
        asset = V5AssetRecord(
            "box3_v5_base_model", "base_model", path_ref,
            sha256_text(str(selected or path_ref)), expected_sha, "file", None, False, None,
            "PARTIAL_REAL_ASSET_VOLUME_MISSING",
        )
        return V5AssetManifest(V5_SCHEMA_VERSION, "PARTIAL_REAL_ASSET_VOLUME_MISSING", V5_MODEL_NAME, MODEL_LINEAGE, asset, True)

    if _path_has_v4_reference(str(selected)):
        actual_sha = sha256_file(selected)
        asset = V5AssetRecord(
            "box3_v5_base_model", "base_model", path_ref,
            sha256_text(str(selected)), actual_sha, "file", selected.stat().st_size,
            not os.access(selected, os.W_OK), _now(), "BLOCK_V4_DEFAULT_REFERENCE",
        )
        return V5AssetManifest(V5_SCHEMA_VERSION, "BLOCKED", V5_MODEL_NAME, MODEL_LINEAGE, asset, False)

    actual_sha = sha256_file(selected)
    readonly = (not os.access(selected, os.W_OK)) if readonly_required else True
    if actual_sha != V5_Q4_K_M_SHA256_FULL:
        fail = "BLOCK_MODEL_ASSET_SHA_MISMATCH"
        status = "BLOCKED"
    elif not readonly:
        fail = "BLOCK_MODEL_ASSET_MISSING"
        status = "BLOCKED"
    else:
        fail = None
        status = "ASSET_INVENTORY_PASS"

    asset = V5AssetRecord(
        "box3_v5_base_model", "base_model", path_ref,
        sha256_text(str(selected)), actual_sha, "file", selected.stat().st_size,
        readonly, _now(), fail,
    )
    return V5AssetManifest(V5_SCHEMA_VERSION, status, V5_MODEL_NAME, MODEL_LINEAGE, asset, True)

def manifest_allows_v5_real(manifest: V5AssetManifest | dict[str, Any]) -> bool:
    data = manifest.to_dict() if isinstance(manifest, V5AssetManifest) else manifest
    try:
        asset = data["asset"]
        return (
            data.get("schema_version") == V5_SCHEMA_VERSION
            and data.get("status") == "ASSET_INVENTORY_PASS"
            and data.get("model_choice") == V5_MODEL_NAME
            and data.get("model_lineage", {}).get("runtime_lora_stack_allowed") is False
            and asset.get("sha256_full") == V5_Q4_K_M_SHA256_FULL
            and asset.get("sha_scope") == "file"
            and isinstance(asset.get("size_bytes"), int)
            and asset.get("size_bytes") > 0
            and asset.get("readonly_verified") is True
            and data.get("v4_default_reference_zero") is True
        )
    except Exception:
        return False
