#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from butler_pc_core.cards.box3.human_approval_sealed import (
    APPROVAL_SCOPE_KIND_BOX3_MODEL,
    APPROVAL_SCHEMA_V2,
    APPROVED_MODEL_ROLE_BOX3_DRAFT,
    MODEL_SCOPE_STATUS,
    display_sha256_digest,
)
from butler_pc_core.cards.box3.model_identity import compute_box3_model_identity, get_runtime_device_id_digest


def sha256_text(namespace: str, value: str) -> str:
    return display_sha256_digest(hashlib.sha256((namespace + value).encode("utf-8")).hexdigest(), prefix=True)


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("MANIFEST_SCHEMA_INVALID")
    return data


def validate_manifest(manifest: dict[str, Any], model_digest: str) -> None:
    if manifest.get("schema_version") != "butler.box3.sealed_model_manifest.v1":
        raise SystemExit("MANIFEST_SCHEMA_INVALID")
    if manifest.get("status") != "SEALED":
        raise SystemExit("MODEL_NOT_SEALED")
    if manifest.get("approved_for_runtime") is not True:
        raise SystemExit("MODEL_NOT_APPROVED_FOR_RUNTIME")
    if display_sha256_digest(str(manifest.get("model_sha256") or ""), prefix=True) != display_sha256_digest(model_digest, prefix=True):
        raise SystemExit("MANIFEST_MODEL_DIGEST_MISMATCH")


def atomic_write_json(path: Path, payload: dict[str, Any], *, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise SystemExit("APPROVAL_FILE_EXISTS")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate digest-only Box3 model-scope human approval.")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--sealed-manifest", required=True)
    parser.add_argument("--approver", required=True)
    parser.add_argument("--out", default=str(Path.home() / ".butler" / "box3" / "human_approval_v2.json"))
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.days < 1 or args.days > 90:
        raise SystemExit("DAYS_OUT_OF_RANGE")

    identity = compute_box3_model_identity(args.model_path)
    manifest = read_json(Path(args.sealed_manifest))
    validate_manifest(manifest, identity.model_path_digest)
    device_digest = get_runtime_device_id_digest()
    if not device_digest:
        raise SystemExit("DEVICE_DIGEST_UNAVAILABLE")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires = now + timedelta(days=args.days)
    payload = {
        "schema_version": APPROVAL_SCHEMA_V2,
        "approval_mode": "model_scope",
        "approval_scope_kind": APPROVAL_SCOPE_KIND_BOX3_MODEL,
        "approved_model_role": APPROVED_MODEL_ROLE_BOX3_DRAFT,
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": sha256_text("box3.approver.v1:", args.approver),
        "device_id_digest": device_digest,
        "approval_scope_digest": identity.model_path_digest,
        "approved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": MODEL_SCOPE_STATUS,
    }
    atomic_write_json(Path(args.out), payload, force=args.force)
    print("BOX3_MODEL_SCOPE_APPROVAL_CREATED=1")
    print(f"model_digest_prefix={identity.model_path_digest[:23]}")
    print(f"device_digest_prefix={device_digest[:23]}")
    print(f"approval_path={Path(args.out).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
