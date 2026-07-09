#!/usr/bin/env python3
"""Box3 model-scope approval verifier (v1.2 §5.2).

approval file · sealed manifest · physical model · eval summary · device digest 를
모두 검증한다. 실패 reason 은 고정 enum 으로만 출력한다(원문·경로·사용자명 0, meta-only).
성공 시 `BOX3_MODEL_SCOPE_APPROVAL_OK=1`, 실패 시 `BOX3_MODEL_SCOPE_APPROVAL_OK=0` + reason.
AGENTS.md: verify 출력은 판정만(키=0/1 + 짧은 ERROR_CODE).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from butler_pc_core.cards.box3.actual_contracts import canonical_sha256, is_canonical_sha256, stable_json_digest
from butler_pc_core.cards.box3.model_identity import hash_model_file_for_security, read_runtime_device_id_digest

APPROVAL_KEYS = frozenset(
    {
        "schema_version",
        "approval_mode",
        "allow",
        "kill_switch_enabled",
        "revoked",
        "approved_by_digest",
        "approval_scope_digest",
        "device_id_digest",
        "model_manifest_digest",
        "model_path_digest",
        "approved_at",
        "expires_at",
        "status",
    }
)
MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "model_role",
        "model_name",
        "model_version",
        "model_digest",
        "model_size_bytes",
        "eval_summary_sha256",
        "eval_suite",
        "sealed_at",
        "sealed_by_digest",
        "source_commit",
    }
)
_RFC3339Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ZERO_DIGEST = "sha256:" + "0" * 64
_FORBIDDEN_SUBSTR = ("pending", "placeholder", "unknown", "todo", "tbd")


class VerifyError(Exception):
    """고정 reason enum 만 message 로 사용한다."""


def _parse_rfc3339z(value: object) -> datetime | None:
    if not isinstance(value, str) or not _RFC3339Z.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return canonical_sha256(h.hexdigest())


def validate_sealed_manifest(manifest: dict) -> None:
    if not isinstance(manifest, dict) or set(manifest.keys()) != MANIFEST_KEYS:
        raise VerifyError("MANIFEST_SCHEMA_INVALID")
    if manifest.get("model_role") != "box3_draft":
        raise VerifyError("MANIFEST_SCHEMA_INVALID")
    if not is_canonical_sha256(manifest.get("model_digest")) or manifest["model_digest"] == _ZERO_DIGEST:
        raise VerifyError("MANIFEST_SCHEMA_INVALID")
    if not is_canonical_sha256(manifest.get("eval_summary_sha256")) or manifest["eval_summary_sha256"] == _ZERO_DIGEST:
        raise VerifyError("MANIFEST_SCHEMA_INVALID")
    if not is_canonical_sha256(manifest.get("sealed_by_digest")):
        raise VerifyError("MANIFEST_SCHEMA_INVALID")
    if not isinstance(manifest.get("model_size_bytes"), int) or manifest["model_size_bytes"] <= 0:
        raise VerifyError("MANIFEST_SCHEMA_INVALID")
    if _parse_rfc3339z(manifest.get("sealed_at")) is None:
        raise VerifyError("MANIFEST_SCHEMA_INVALID")
    blob = json.dumps(manifest, ensure_ascii=False).casefold()
    if any(bad in blob for bad in _FORBIDDEN_SUBSTR):
        raise VerifyError("MANIFEST_SCHEMA_INVALID")


def validate_approval_file(path: Path) -> dict:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise VerifyError("APPROVAL_SCHEMA_INVALID") from exc
    if mode != 0o600:
        raise VerifyError("APPROVAL_FILE_PERMISSION_INVALID")
    try:
        approval = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifyError("APPROVAL_SCHEMA_INVALID") from exc
    if not isinstance(approval, dict) or set(approval.keys()) != APPROVAL_KEYS:
        raise VerifyError("APPROVAL_SCHEMA_INVALID")
    if approval.get("schema_version") != "box3.human_approval.v1":
        raise VerifyError("APPROVAL_SCHEMA_INVALID")
    for key in ("allow", "kill_switch_enabled", "revoked"):
        if not isinstance(approval.get(key), bool):
            raise VerifyError("APPROVAL_SCHEMA_INVALID")
    for key in ("approved_by_digest", "approval_scope_digest", "device_id_digest", "model_manifest_digest", "model_path_digest"):
        if not is_canonical_sha256(approval.get(key)):
            raise VerifyError("APPROVAL_SCHEMA_INVALID")
    if approval.get("approval_mode") != "model_scope":
        raise VerifyError("APPROVAL_MODE_INVALID")
    if approval.get("status") != "APPROVED_MODEL_SCOPE":
        raise VerifyError("APPROVAL_SCHEMA_INVALID")
    if approval.get("allow") is not True or approval.get("kill_switch_enabled") is not False or approval.get("revoked") is not False:
        raise VerifyError("APPROVAL_SCHEMA_INVALID")
    approved_at = _parse_rfc3339z(approval.get("approved_at"))
    expires_at = _parse_rfc3339z(approval.get("expires_at"))
    if approved_at is None or expires_at is None:
        raise VerifyError("APPROVAL_SCHEMA_INVALID")
    days = (expires_at - approved_at).days
    if days <= 0 or days > 90:
        raise VerifyError("APPROVAL_SCHEMA_INVALID")
    if expires_at <= datetime.now(timezone.utc):
        raise VerifyError("APPROVAL_SCHEMA_INVALID")
    return approval


def verify(approval_path: Path, manifest_path: Path, model_path: Path, eval_summary_path: Path) -> None:
    approval = validate_approval_file(approval_path)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifyError("MANIFEST_SCHEMA_INVALID") from exc
    validate_sealed_manifest(manifest)

    # 물리 GGUF 재해싱 (fd 기반 TOCTOU-hardened). symlink/변경/swap 은 고정 reason 으로 raise.
    try:
        identity = hash_model_file_for_security(str(model_path))
    except ValueError as exc:
        raise VerifyError(str(exc)) from exc
    if identity.model_digest != manifest["model_digest"]:
        raise VerifyError("PHYSICAL_MODEL_DIGEST_MISMATCH")

    # eval_summary 재해싱
    try:
        eval_digest = _sha256_file(eval_summary_path)
    except OSError as exc:
        raise VerifyError("EVAL_SUMMARY_DIGEST_MISMATCH") from exc
    if eval_digest != manifest["eval_summary_sha256"]:
        raise VerifyError("EVAL_SUMMARY_DIGEST_MISMATCH")

    # approval ↔ manifest 결속 (model_scope: scope digest == 물리 model_digest)
    if approval["approval_scope_digest"] != identity.model_digest:
        raise VerifyError("APPROVAL_SCOPE_DIGEST_MISMATCH")
    if approval["model_manifest_digest"] != stable_json_digest(manifest):
        raise VerifyError("APPROVAL_SCOPE_DIGEST_MISMATCH")

    # device digest read-only 검증 (검증 경로는 생성 0)
    device_digest = read_runtime_device_id_digest()
    if device_digest is None:
        raise VerifyError("DEVICE_DIGEST_UNAVAILABLE")
    if approval["device_id_digest"] != device_digest:
        raise VerifyError("DEVICE_DIGEST_MISMATCH")


def main() -> int:
    parser = argparse.ArgumentParser(description="Box3 model-scope approval verifier (meta-only).")
    parser.add_argument("--approval", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--eval-summary", required=True)
    args = parser.parse_args()
    try:
        verify(Path(args.approval), Path(args.manifest), Path(args.model), Path(args.eval_summary))
    except VerifyError as exc:
        print("BOX3_MODEL_SCOPE_APPROVAL_OK=0")
        print(f"REASON={exc}")
        return 1
    print("BOX3_MODEL_SCOPE_APPROVAL_OK=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
