from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .v7_constants import (
    BASE_MODEL_NAME,
    BASE_MODEL_PATH_ENV,
    BASE_MODEL_SHA256_FULL,
    BASE_MODEL_SHA_SCOPE,
    BOX3_BASE_MODEL_VERSION,
    HELPER3_5_EMBEDDED_IN_BASE,
    HELPER3_5_RUNTIME_STACK_ALLOWED,
    MODEL_LINEAGE,
    PRODUCTION_CLAIM_ALLOWED,
    V7_F16_SHA256_FULL,
    V7_MODEL_NAME,
)
from .v7_fail_class import (
    BLOCK_HELPER35_DOUBLE_STACK_RISK,
    BLOCK_MODEL_ASSET_SHA_SCOPE_INVALID,
    BLOCK_V4_DEFAULT_REFERENCE,
    BLOCK_V5_DEFAULT_RESIDUE,
    BLOCK_V7_SHA_MISMATCH,
    PARTIAL_REAL_ASSET_VOLUME_MISSING,
)
from .v7_security import assert_digest_only, is_bare_sha256, sha256_text, stable_json_digest


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _path_has_v4_reference(value: str) -> bool:
    lowered = value.casefold()
    return "v4" in lowered or "v4-rt" in lowered or "butler-1.7b-v4" in lowered


def _path_has_v5_reference(value: str) -> bool:
    lowered = value.casefold()
    return "butler-1.7b-v5" in lowered or "v5-q4" in lowered or "5e233aab" in lowered


def helper35_runtime_stack_requested(env: dict[str, str] | None = None) -> bool:
    e = env or os.environ
    if e.get("BUTLER_BOX3_ALLOW_HELPER35_MULTI_LORA_STACK") in {"1", "true", "TRUE", "yes"}:
        return True
    for key, value in e.items():
        if "LORA" in key.upper() and any(marker in str(value).casefold() for marker in ("helper3", "helper5", "ad852bbb", "92e8454f")):
            return True
    return False


@dataclass(frozen=True)
class V7AssetVerdict:
    allowed: bool
    status: str
    fail_class: str | None
    model_version: str
    model_name: str
    path_ref: str
    path_digest: str | None
    sha256_full: str | None
    expected_sha256_full: str
    sha_scope: str
    size_bytes: int | None
    readonly_verified: bool
    f16_reference_sha256_full: str
    helper3_5_embedded_in_base: bool
    helper3_5_runtime_stack_allowed: bool
    production_claim_allowed: bool
    model_lineage_digest: str
    measured_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        assert_digest_only(payload)
        return payload


def verify_v7_q4_asset(*, path_value: str | None = None, env: dict[str, str] | None = None, readonly_required: bool = True) -> V7AssetVerdict:
    e = env or os.environ
    selected_path = path_value if path_value is not None else e.get(BASE_MODEL_PATH_ENV)
    path_ref = f"ref:{BASE_MODEL_PATH_ENV}"
    lineage_digest = stable_json_digest(MODEL_LINEAGE)
    if helper35_runtime_stack_requested(e):
        return _verdict(False, "BLOCKED", BLOCK_HELPER35_DOUBLE_STACK_RISK, path_ref, selected_path, None, None, False, lineage_digest)
    if not is_bare_sha256(BASE_MODEL_SHA256_FULL) or BASE_MODEL_SHA_SCOPE != "file":
        return _verdict(False, "BLOCKED", BLOCK_MODEL_ASSET_SHA_SCOPE_INVALID, path_ref, selected_path, None, None, False, lineage_digest)
    if selected_path and _path_has_v4_reference(selected_path):
        return _verdict(False, "BLOCKED", BLOCK_V4_DEFAULT_REFERENCE, path_ref, selected_path, None, None, False, lineage_digest)
    if selected_path and _path_has_v5_reference(selected_path):
        return _verdict(False, "BLOCKED", BLOCK_V5_DEFAULT_RESIDUE, path_ref, selected_path, None, None, False, lineage_digest)
    if not selected_path:
        return _verdict(False, PARTIAL_REAL_ASSET_VOLUME_MISSING, PARTIAL_REAL_ASSET_VOLUME_MISSING, path_ref, None, None, None, False, lineage_digest)
    path = Path(selected_path)
    if not path.exists() or not path.is_file():
        return _verdict(False, PARTIAL_REAL_ASSET_VOLUME_MISSING, PARTIAL_REAL_ASSET_VOLUME_MISSING, path_ref, selected_path, None, None, False, lineage_digest)
    actual = sha256_file(path)
    size = path.stat().st_size
    if actual != BASE_MODEL_SHA256_FULL:
        return _verdict(False, "BLOCKED", BLOCK_V7_SHA_MISMATCH, path_ref, selected_path, actual, size, False, lineage_digest)
    readonly = (not os.access(path, os.W_OK)) if readonly_required else True
    return _verdict(True, "ASSET_INVENTORY_PASS", None, path_ref, selected_path, actual, size, readonly, lineage_digest)


def _verdict(allowed: bool, status: str, fail_class: str | None, path_ref: str, path_value: str | None, actual_sha: str | None, size: int | None, readonly: bool, lineage_digest: str) -> V7AssetVerdict:
    return V7AssetVerdict(
        allowed=allowed,
        status=status,
        fail_class=fail_class,
        model_version=BOX3_BASE_MODEL_VERSION,
        model_name=BASE_MODEL_NAME,
        path_ref=path_ref,
        path_digest=sha256_text(path_value) if path_value else None,
        sha256_full=actual_sha,
        expected_sha256_full=BASE_MODEL_SHA256_FULL,
        sha_scope=BASE_MODEL_SHA_SCOPE,
        size_bytes=size,
        readonly_verified=readonly,
        f16_reference_sha256_full=V7_F16_SHA256_FULL,
        helper3_5_embedded_in_base=HELPER3_5_EMBEDDED_IN_BASE,
        helper3_5_runtime_stack_allowed=HELPER3_5_RUNTIME_STACK_ALLOWED,
        production_claim_allowed=PRODUCTION_CLAIM_ALLOWED,
        model_lineage_digest=lineage_digest,
        measured_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat() if actual_sha else None,
    )
