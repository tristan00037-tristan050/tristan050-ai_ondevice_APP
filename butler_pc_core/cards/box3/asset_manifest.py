from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re


FULL_SHA_RE = re.compile(r"^[a-f0-9]{64}$")

HELPER3_SHA = "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0"
EXPECTED_ASSET_MANIFEST_SCHEMA_VERSION = "box3.asset_manifest.v1"
ASSET_INVENTORY_PASS_STATUS = "ASSET_INVENTORY_PASS"
CONTRACT_ONLY_ASSET_STATUS = "PARTIAL_CONTRACT_ONLY_ASSET_INVENTORY_PENDING"

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


def is_full_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(FULL_SHA_RE.fullmatch(value))


def validate_asset_record(record: Box3AssetRecord) -> list[str]:
    errors: list[str] = []
    if not isinstance(record.asset_name, str):
        errors.append("ASSET_NAME_INVALID")
    if not isinstance(record.role, str):
        errors.append("ASSET_ROLE_INVALID")
    if not isinstance(record.display_sha_prefix, str):
        errors.append("DISPLAY_SHA_PREFIX_INVALID")
    if record.asset_path is not None and not isinstance(record.asset_path, str):
        errors.append("ASSET_PATH_INVALID")
    if record.sha256_full is not None and not isinstance(record.sha256_full, str):
        errors.append("SHA256_FULL_INVALID")
    if record.measured_at is not None and not isinstance(record.measured_at, str):
        errors.append("MEASURED_AT_INVALID")
    if not isinstance(record.measured_by, str):
        errors.append("MEASURED_BY_INVALID")
    if not isinstance(record.source_metadata_files, list) or not all(
        isinstance(item, str) for item in record.source_metadata_files
    ):
        errors.append("SOURCE_METADATA_FILES_INVALID")
    if not isinstance(record.interface_inventory_status, str):
        errors.append("INTERFACE_INVENTORY_STATUS_INVALID")
    if not isinstance(record.real_claim_allowed, bool):
        errors.append("REAL_CLAIM_ALLOWED_INVALID")
    if record.fail_class is not None and not isinstance(record.fail_class, str):
        errors.append("FAIL_CLASS_INVALID")
    if not isinstance(record.sha_scope, str) or record.sha_scope not in {"file", "directory_manifest", "unknown"}:
        errors.append("SHA_SCOPE_INVALID")
    if record.real_claim_allowed:
        if not isinstance(record.sha_scope, str) or record.sha_scope not in {"file", "directory_manifest"}:
            errors.append("SHA_SCOPE_REQUIRED_FOR_REAL")
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
            # Codex P2 정정 (2026-06-01, PR #770): 인계 폴더의 로컬 절대경로/모델 파일명 평문 누출 제거.
            # 자산 위치는 ref 로만 표기하고 로컬경로·모델 파일명을 소스·evidence 에 두지 않는다.
            asset_path="ref:BUTLER_HELPER3_FORMAT_PATH",
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
        "schema_version": EXPECTED_ASSET_MANIFEST_SCHEMA_VERSION,
        "status": CONTRACT_ONLY_ASSET_STATUS,
        "real_claim_allowed": False,
        "state_gate": "CONTRACT_ONLY",
        "created_at": now,
        "assets": [asdict(record) for record in records],
        "asset_errors": asset_errors,
        "honest_disclosure": "helper3 file SHA was measured locally; helper4/helper7/helper8 full SHA and interface inventory are not available in the provided Box3 folder.",
    }


def load_asset_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_block_reason(manifest: dict[str, Any]) -> str | None:
    """Return a blocking fail_class for malformed/drifted manifests, otherwise None.

    CONTRACT_ONLY 상태 자체는 허용하지만, caller 가 주입한 manifest 의 schema/status/row shape
    drift 는 조용히 demotion 하지 않고 pipeline 이 BLOCK 으로 표면화해야 한다.
    """
    if not isinstance(manifest, dict):
        return "BLOCK_ASSET_MANIFEST_INVALID"
    if manifest.get("schema_version") != EXPECTED_ASSET_MANIFEST_SCHEMA_VERSION:
        return "BLOCK_ASSET_MANIFEST_SCHEMA_DRIFT"

    status = manifest.get("status")
    real_claim_allowed = manifest.get("real_claim_allowed")
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        return "BLOCK_ASSET_MANIFEST_INVALID"

    names: list[str] = []
    records: list[Box3AssetRecord] = []
    for item in assets:
        try:
            record = Box3AssetRecord(**item)
        except TypeError:
            return "BLOCK_ASSET_MANIFEST_INVALID"
        if validate_asset_record(record):
            return "BLOCK_ASSET_MANIFEST_INVALID"
        names.append(record.asset_name)
        records.append(record)
    if len(names) != len(set(names)) or set(names) != set(REQUIRED_ASSET_NAMES):
        return "BLOCK_ASSET_MANIFEST_INVALID"

    if status == CONTRACT_ONLY_ASSET_STATUS and real_claim_allowed is False:
        if any(record.real_claim_allowed or record.fail_class is None for record in records):
            return "BLOCK_ASSET_MANIFEST_CONTRADICTORY_ROWS"
        return None
    if status != ASSET_INVENTORY_PASS_STATUS:
        return "BLOCK_ASSET_MANIFEST_STATUS_DRIFT"
    if real_claim_allowed is not True:
        return "BLOCK_ASSET_MANIFEST_REAL_FLAG_DRIFT"
    if not manifest_allows_real(manifest):
        return "BLOCK_ASSET_MANIFEST_INVALID"
    return None


def manifest_allows_real(manifest: dict[str, Any]) -> bool:
    # Codex P2 정정 (2026-06-01, PR #770): asset rows 만 보고 top-level inventory 상태를
    # 무시하면, status/state_gate 가 pending/blocked 인 드리프트 manifest 가 real_claim_allowed:true
    # 만으로 real runner 를 활성화하던 fail-open 결함. manifest 수준 status 가 ASSET_INVENTORY_PASS
    # 일 때만 real 을 허용한다(fail-closed asset inventory gate).
    # Codex P1 정정 (2026-06-01, PR #770): schema drift fail-closed — 계약 버전이 정본과
    # 다르거나 누락된 manifest(disk/API 주입 포함)는 real 모드 입력으로 받지 않는다.
    if not isinstance(manifest, dict):
        return False
    if manifest.get("schema_version") != EXPECTED_ASSET_MANIFEST_SCHEMA_VERSION:
        return False
    if manifest.get("status") != ASSET_INVENTORY_PASS_STATUS:
        return False
    if manifest.get("real_claim_allowed") is not True:
        return False
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        return False
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
        # Codex P1 정정 (2026-06-01, PR #770): top-level real_claim_allowed=true 여도 개별 row 가
        # real_claim_allowed=false 거나 blocking fail_class 를 가지면 real 불가(row 수준 fail-closed).
        if not record.real_claim_allowed or record.fail_class is not None:
            return False
        names.append(record.asset_name)
    if len(names) != len(set(names)) or set(names) != set(REQUIRED_ASSET_NAMES):
        return False
    return True
