#!/usr/bin/env python3
"""Box3 model-scope approval generator (v1.2 §5.1).

sealed manifest 검증 → 물리 GGUF/eval_summary 재해싱 일치 확인 → exact-schema 승인 파일을
temp → fsync → os.replace → chmod 0600 순 atomic 으로 출력한다. approved_by 원문은 저장하지
않고 approved_by_digest 만 저장한다. device digest 는 프로비저닝 경로에서만 생성한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(_REPO_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from butler_pc_core.cards.box3.actual_contracts import canonical_sha256, stable_json_digest
from butler_pc_core.cards.box3.model_identity import (
    ensure_runtime_device_id_digest,
    hash_model_file_for_security,
    write_file_atomic_0600,
)
from verify_box3_model_scope_approval import VerifyError, _sha256_file, validate_sealed_manifest


def _rfc3339z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate(*, manifest_path: Path, model_path: Path, eval_summary_path: Path, approved_by: str, days: int, out_path: Path) -> dict:
    if days <= 0 or days > 90:
        raise VerifyError("APPROVAL_SCHEMA_INVALID")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_sealed_manifest(manifest)

    identity = hash_model_file_for_security(str(model_path))
    if identity.model_digest != manifest["model_digest"]:
        raise VerifyError("PHYSICAL_MODEL_DIGEST_MISMATCH")
    if identity.size_bytes != manifest["model_size_bytes"]:
        raise VerifyError("PHYSICAL_MODEL_DIGEST_MISMATCH")
    if _sha256_file(eval_summary_path) != manifest["eval_summary_sha256"]:
        raise VerifyError("EVAL_SUMMARY_DIGEST_MISMATCH")

    device_digest = ensure_runtime_device_id_digest()  # 프로비저닝 전용 생성 허용
    now = datetime.now(timezone.utc)
    approval = {
        "schema_version": "box3.human_approval.v1",
        "approval_mode": "model_scope",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": canonical_sha256(hashlib.sha256(approved_by.encode("utf-8")).hexdigest()),
        "approval_scope_digest": identity.model_digest,
        "device_id_digest": device_digest,
        "model_manifest_digest": stable_json_digest(manifest),
        "model_path_digest": identity.model_path_digest,
        "approved_at": _rfc3339z(now),
        "expires_at": _rfc3339z(now + timedelta(days=days)),
        "status": "APPROVED_MODEL_SCOPE",
    }
    write_file_atomic_0600(out_path, json.dumps(approval, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return approval


def main() -> int:
    parser = argparse.ArgumentParser(description="Box3 model-scope approval generator (provisioning only).")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--eval-summary", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        generate(
            manifest_path=Path(args.manifest),
            model_path=Path(args.model),
            eval_summary_path=Path(args.eval_summary),
            approved_by=args.approved_by,
            days=args.days,
            out_path=Path(args.out),
        )
    except (VerifyError, ValueError) as exc:
        print("BOX3_MODEL_SCOPE_APPROVAL_GENERATED=0")
        print(f"REASON={exc}")
        return 1
    print("BOX3_MODEL_SCOPE_APPROVAL_GENERATED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
