
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

ShaScope = Literal["file", "directory_manifest"]
AssetStatus = Literal[
    "PASS",
    "FULL_SHA_PENDING",
    "INTERFACE_INVENTORY_PENDING",
    "BLOCK_SHA_INVALID",
    "BLOCK_SCOPE_INVALID",
]

_SHA64 = set("0123456789abcdef")

HELPER3_FORMAT_FULL_SHA = "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0"

@dataclass(frozen=True)
class Box3Asset:
    asset_name: str
    role: str
    asset_path_ref: str
    sha256_full: str | None
    sha_scope: ShaScope | None
    source_metadata_files: list[str] = field(default_factory=list)
    interface_status: str = "inventory_pending"

    def status(self) -> AssetStatus:
        if self.sha256_full is None:
            return "FULL_SHA_PENDING"
        if not is_full_sha256(self.sha256_full):
            return "BLOCK_SHA_INVALID"
        if self.sha_scope not in ("file", "directory_manifest"):
            return "BLOCK_SCOPE_INVALID"
        # Codex P1 정정 (2026-06-01, PR #770): SHA/scope 만 보고 PASS 를 반환하면, 해시가 채워져도
        # interface inventory 가 미완(예: "full_sha_and_interface_inventory_required")인 자산이
        # manifest.status=ASSET_INVENTORY_PASS 로 승격되어 real 로 반환되던 결함. interface_status 가
        # "pass" 가 아니면 PASS 가 아니라 INTERFACE_INVENTORY_PENDING 으로 fail-closed.
        if self.interface_status != "pass":
            return "INTERFACE_INVENTORY_PENDING"
        return "PASS"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["sha_status"] = self.status()
        return out

@dataclass(frozen=True)
class Box3AssetManifest:
    schema_version: str
    assets: list[Box3Asset]
    model_artifact_included: bool = False
    training_scope_included: bool = False

    @property
    def status(self) -> str:
        statuses = [asset.status() for asset in self.assets]
        if any(status.startswith("BLOCK") for status in statuses):
            return "BLOCK_ASSET_MANIFEST"
        if any(status in ("FULL_SHA_PENDING", "INTERFACE_INVENTORY_PENDING") for status in statuses):
            return "PARTIAL_ASSET_INVENTORY_PENDING"
        return "ASSET_INVENTORY_PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "model_artifact_included": self.model_artifact_included,
            "training_scope_included": self.training_scope_included,
            "assets": [asset.to_dict() for asset in self.assets],
        }

def is_full_sha256(value: str | None) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in _SHA64 for ch in value)

def build_default_manifest() -> Box3AssetManifest:
    return Box3AssetManifest(
        schema_version="box3.asset_manifest.v1",
        assets=[
            Box3Asset(
                asset_name="helper3_format",
                role="company_format_application",
                asset_path_ref="BUTLER_HELPER3_FORMAT_PATH",
                sha256_full=HELPER3_FORMAT_FULL_SHA,
                sha_scope="file",
                source_metadata_files=["adapter_config.json", "README.md"],
                interface_status="consumer_wrapper_contract_ready",
            ),
            Box3Asset(
                asset_name="helper4_grounding",
                role="grounding_verification",
                asset_path_ref="BUTLER_HELPER4_GROUNDING_PATH",
                sha256_full=None,
                sha_scope=None,
                source_metadata_files=["README.md", "adapter_config.json", "metadata.json"],
                interface_status="full_sha_and_interface_inventory_required",
            ),
            Box3Asset(
                asset_name="helper7_extract",
                role="table_figure_and_evidence_extraction",
                asset_path_ref="BUTLER_HELPER7_EXTRACT_PATH",
                sha256_full=None,
                sha_scope=None,
                source_metadata_files=["README.md", "adapter_config.json", "metadata.json"],
                interface_status="full_sha_and_interface_inventory_required",
            ),
            Box3Asset(
                asset_name="helper8_style",
                role="company_style_profile",
                asset_path_ref="BUTLER_HELPER8_STYLE_PATH",
                sha256_full=None,
                sha_scope=None,
                source_metadata_files=["README.md", "adapter_config.json", "metadata.json"],
                interface_status="full_sha_and_interface_inventory_required",
            ),
        ],
    )

def manifest_digest(manifest: Box3AssetManifest) -> str:
    encoded = json.dumps(manifest.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def validate_manifest_payload(payload: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if payload.get("schema_version") != "box3.asset_manifest.v1":
        reasons.append("SCHEMA_VERSION_INVALID")
    assets = payload.get("assets")
    if not isinstance(assets, list) or len(assets) != 4:
        reasons.append("ASSET_COUNT_INVALID")
    else:
        names = {asset.get("asset_name") for asset in assets if isinstance(asset, dict)}
        required = {"helper3_format", "helper4_grounding", "helper7_extract", "helper8_style"}
        if names != required:
            reasons.append("ASSET_NAMES_INVALID")
        for asset in assets:
            sha = asset.get("sha256_full")
            if sha is not None and not is_full_sha256(sha):
                reasons.append(f"{asset.get('asset_name', 'unknown')}:SHA_NOT_FULL_64")
            scope = asset.get("sha_scope")
            if sha is not None and scope not in ("file", "directory_manifest"):
                reasons.append(f"{asset.get('asset_name', 'unknown')}:SHA_SCOPE_INVALID")
    if payload.get("model_artifact_included") is not False:
        reasons.append("MODEL_ARTIFACT_INCLUDED")
    if payload.get("training_scope_included") is not False:
        reasons.append("TRAINING_SCOPE_INCLUDED")
    return ("PASS" if not reasons else "BLOCK", reasons)

def write_default_manifest(path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(build_default_manifest().to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
