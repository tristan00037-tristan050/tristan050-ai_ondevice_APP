from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re


FULL_SHA_RE = re.compile(r"^[a-f0-9]{64}$")

HELPER3_SHA = "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0"

# real 모드에 필요한 4개 필수 helper 자산. manifest_allows_real 이 정확히 1회씩 존재(중복 0)를 강제.
REQUIRED_ASSET_NAMES = (
    "helper3_format",
    "helper4_grounding",
    "helper7_table_figure",
    "helper8_company_style",
)


@dataclass(frozen=True)
class Box3AssetRecord:
    asset_name: str
    role: str
    display_sha_prefix: str
    asset_path: str | None
    sha256_full: str | None
    sha_scope: str
    measured_at: str | None
    measured_by: str
    source_metadata_files: list[str]
    interface_inventory_status: str
    real_claim_allowed: bool
    fail_class: str | None


def is_full_sha256(value: str | None) -> bool:
    return bool(value and FULL_SHA_RE.fullmatch(value))


def validate_asset_record(record: Box3AssetRecord) -> list[str]:
    errors: list[str] = []
    if record.sha_scope not in {"file", "directory_manifest", "unknown"}:
        errors.append("SHA_SCOPE_INVALID")
    if record.real_claim_allowed:
        if not is_full_sha256(record.sha256_full):
            errors.append("FULL_SHA_REQUIRED_FOR_REAL")
        if record.interface_inventory_status != "pass":
            errors.append("INTERFACE_INVENTORY_REQUIRED_FOR_REAL")
    if record.sha256_full is not None and not is_full_sha256(record.sha256_full):
        errors.append("SHORT_OR_INVALID_SHA_FORBIDDEN")
    return errors


def build_contract_only_asset_manifest(measured_at: str | None = None) -> dict[str, Any]:
    now = measured_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records = [
        Box3AssetRecord(
            asset_name="helper3_format",
            role="company_format_application",
            display_sha_prefix="92e8454f...",
            asset_path="~/Desktop/도우미폴더/넘겨줄도우미모델/box2b_v5_outputs/rewrite/adapter/box2b_v5_rewrite/adapter_model.safetensors",
            sha256_full=HELPER3_SHA,
            sha_scope="file",
            measured_at=now,
            measured_by="codex_local_shasum",
            source_metadata_files=["adapter_config.json"],
            interface_inventory_status="contract_sample_only",
            real_claim_allowed=False,
            fail_class="INTERFACE_INVENTORY_PENDING",
        ),
        Box3AssetRecord(
            asset_name="helper4_grounding",
            role="grounding_verification",
            display_sha_prefix="b7b1af0e...",
            asset_path=None,
            sha256_full=None,
            sha_scope="unknown",
            measured_at=None,
            measured_by="not_measured",
            source_metadata_files=[],
            interface_inventory_status="missing_asset_path",
            real_claim_allowed=False,
            fail_class="BLOCK_FULL_SHA_NOT_MEASURED",
        ),
        Box3AssetRecord(
            asset_name="helper7_table_figure",
            role="evidence_extraction",
            display_sha_prefix="8b034549...",
            asset_path=None,
            sha256_full=None,
            sha_scope="unknown",
            measured_at=None,
            measured_by="not_measured",
            source_metadata_files=[],
            interface_inventory_status="missing_asset_path",
            real_claim_allowed=False,
            fail_class="BLOCK_FULL_SHA_NOT_MEASURED",
        ),
        Box3AssetRecord(
            asset_name="helper8_company_style",
            role="company_style_application",
            display_sha_prefix="7d4f8311...",
            asset_path=None,
            sha256_full=None,
            sha_scope="unknown",
            measured_at=None,
            measured_by="not_measured",
            source_metadata_files=[],
            interface_inventory_status="missing_asset_path",
            real_claim_allowed=False,
            fail_class="BLOCK_FULL_SHA_NOT_MEASURED",
        ),
    ]
    asset_errors = {record.asset_name: validate_asset_record(record) for record in records}
    return {
        "schema_version": "box3.asset_manifest.v1",
        "status": "PARTIAL_CONTRACT_ONLY_ASSET_INVENTORY_PENDING",
        "real_claim_allowed": False,
        "state_gate": "CONTRACT_ONLY",
        "created_at": now,
        "assets": [asdict(record) for record in records],
        "asset_errors": asset_errors,
        "honest_disclosure": "helper3 file SHA was measured locally; helper4/helper7/helper8 full SHA and interface inventory are not available in the provided Box3 folder.",
    }


def load_asset_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_allows_real(manifest: dict[str, Any]) -> bool:
    # Codex P2 정정 (2026-06-01, PR #770): asset rows 만 보고 top-level inventory 상태를
    # 무시하면, status/state_gate 가 pending/blocked 인 드리프트 manifest 가 real_claim_allowed:true
    # 만으로 real runner 를 활성화하던 fail-open 결함. manifest 수준 status 가 ASSET_INVENTORY_PASS
    # 일 때만 real 을 허용한다(fail-closed asset inventory gate).
    if manifest.get("status") != "ASSET_INVENTORY_PASS":
        return False
    if manifest.get("real_claim_allowed") is not True:
        return False
    assets = manifest.get("assets", [])
    if len(assets) != 4:
        return False
    # Codex P1 정정 (2026-06-01, PR #770): asset count 만 보면 동일 helper 4중복도 통과하여
    # helper4/7/8 미인벤토리 상태로 real 이 활성화되던 fail-open. 4개 필수 자산이 정확히 1회씩
    # 존재하고(이름 집합·중복 검사), 각 row 가 유효하며, interface inventory 가 pass 여야 real 허용.
    names: list[str] = []
    for item in assets:
        try:
            record = Box3AssetRecord(**item)
        except TypeError:
            return False
        if validate_asset_record(record):
            return False
        if record.interface_inventory_status != "pass":
            return False
        names.append(record.asset_name)
    if len(names) != len(set(names)) or set(names) != set(REQUIRED_ASSET_NAMES):
        return False
    return True

