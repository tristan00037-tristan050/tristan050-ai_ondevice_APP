#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler_pc_core.cards.box3.human_approval_sealed import (
    APPROVAL_SCOPE_KIND_BOX3_MODEL,
    APPROVAL_SCHEMA_V2,
    APPROVED_MODEL_ROLE_BOX3_DRAFT,
    MODEL_SCOPE_STATUS,
    canonical_sha256_digest,
)
from butler_pc_core.cards.box3.model_identity import get_runtime_device_id_digest


def fail(code: str) -> None:
    print("BOX3_MODEL_SCOPE_APPROVAL_OK=0")
    print(f"ERROR_CODE={code}")
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        fail("JSON_INVALID")
    if not isinstance(data, dict):
        fail("JSON_NOT_OBJECT")
    return data


def parse_z(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        fail(code)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        fail(code)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval", required=True)
    parser.add_argument("--sealed-manifest", required=True)
    parser.add_argument("--device-digest")
    args = parser.parse_args()
    approval_path = Path(args.approval)
    manifest_path = Path(args.sealed_manifest)
    if not approval_path.exists():
        fail("APPROVAL_FILE_MISSING")
    try:
        mode = approval_path.stat().st_mode & 0o777
        if mode > 0o640:
            fail("APPROVAL_FILE_MODE_TOO_OPEN")
    except OSError:
        fail("APPROVAL_FILE_STAT_FAILED")
    approval = load_json(approval_path)
    manifest = load_json(manifest_path)
    expected_keys = {
        "schema_version",
        "approval_mode",
        "approval_scope_kind",
        "approved_model_role",
        "allow",
        "kill_switch_enabled",
        "revoked",
        "approved_by_digest",
        "device_id_digest",
        "approval_scope_digest",
        "approved_at",
        "expires_at",
        "status",
    }
    if set(approval) != expected_keys:
        fail("APPROVAL_SCHEMA_INVALID")
    if approval["schema_version"] != APPROVAL_SCHEMA_V2:
        fail("APPROVAL_SCHEMA_INVALID")
    if approval["approval_mode"] != "model_scope":
        fail("APPROVAL_MODE_REQUIRED")
    if approval["approval_scope_kind"] != APPROVAL_SCOPE_KIND_BOX3_MODEL:
        fail("APPROVAL_SCOPE_KIND_INVALID")
    if approval["approved_model_role"] != APPROVED_MODEL_ROLE_BOX3_DRAFT:
        fail("APPROVED_MODEL_ROLE_INVALID")
    if approval["allow"] is not True or approval["kill_switch_enabled"] is not False or approval["revoked"] is not False:
        fail("APPROVAL_FLAGS_INVALID")
    if approval["status"] != MODEL_SCOPE_STATUS:
        fail("APPROVAL_STATUS_INVALID")
    try:
        approved_by = canonical_sha256_digest(approval["approved_by_digest"])
        device = canonical_sha256_digest(approval["device_id_digest"])
        scope = canonical_sha256_digest(approval["approval_scope_digest"])
    except Exception:
        fail("DIGEST_INVALID")
    if not approved_by or not device or not scope:
        fail("DIGEST_INVALID")
    if manifest.get("status") != "SEALED" or manifest.get("approved_for_runtime") is not True:
        fail("MANIFEST_NOT_RUNTIME_APPROVED")
    try:
        manifest_scope = canonical_sha256_digest(str(manifest.get("model_sha256") or ""))
    except Exception:
        fail("MANIFEST_MODEL_DIGEST_INVALID")
    if manifest_scope != scope:
        fail("APPROVAL_SCOPE_DIGEST_MISMATCH")
    runtime_device = args.device_digest or get_runtime_device_id_digest()
    if not runtime_device:
        fail("DEVICE_DIGEST_UNAVAILABLE")
    try:
        if canonical_sha256_digest(runtime_device) != device:
            fail("APPROVAL_DEVICE_MISMATCH")
    except Exception:
        fail("APPROVAL_DEVICE_MISMATCH")
    if parse_z(approval["expires_at"], "EXPIRES_AT_INVALID") <= datetime.now(timezone.utc):
        fail("EXPIRED")
    parse_z(approval["approved_at"], "APPROVED_AT_INVALID")
    print("BOX3_MODEL_SCOPE_APPROVAL_OK=1")
    print(f"approval_digest_prefix=sha256:{scope[:16]}")
    print(f"device_digest_prefix=sha256:{device[:16]}")
    print("raw_path_logged=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
