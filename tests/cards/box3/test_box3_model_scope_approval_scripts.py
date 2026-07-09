"""Box3 model-scope approval 스크립트/매니페스트 계약 테스트 (v1.2 §5·§6·§7)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from butler_pc_core.cards.box3.model_identity import hash_model_file_for_security
import verify_box3_model_scope_approval as V


def _valid_approval(scope_digest: str) -> dict:
    return {
        "schema_version": "box3.human_approval.v1",
        "approval_mode": "model_scope",
        "allow": True,
        "kill_switch_enabled": False,
        "revoked": False,
        "approved_by_digest": "sha256:" + "a" * 64,
        "approval_scope_digest": scope_digest,
        "device_id_digest": "sha256:" + "b" * 64,
        "model_manifest_digest": "sha256:" + "c" * 64,
        "model_path_digest": "sha256:" + "d" * 64,
        "approved_at": "2026-07-09T00:00:00Z",
        "expires_at": "2026-10-07T00:00:00Z",
        "status": "APPROVED_MODEL_SCOPE",
    }


def test_approval_file_exact_schema_unknown_key_rejected(tmp_path):
    approval = _valid_approval("sha256:" + "e" * 64)
    approval["unexpected_extra"] = "x"  # unknown key
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(approval), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(V.VerifyError) as exc:
        V.validate_approval_file(path)
    assert str(exc.value) == "APPROVAL_SCHEMA_INVALID"


def test_approval_file_permission_non_0600_rejected(tmp_path):
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(_valid_approval("sha256:" + "e" * 64)), encoding="utf-8")
    path.chmod(0o644)
    with pytest.raises(V.VerifyError) as exc:
        V.validate_approval_file(path)
    assert str(exc.value) == "APPROVAL_FILE_PERMISSION_INVALID"


def test_approval_days_over_90_rejected(tmp_path):
    approval = _valid_approval("sha256:" + "e" * 64)
    approval["expires_at"] = "2027-07-09T00:00:00Z"  # > 90 일
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(approval), encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(V.VerifyError) as exc:
        V.validate_approval_file(path)
    assert str(exc.value) == "APPROVAL_SCHEMA_INVALID"


def test_manifest_zero_digest_rejected():
    manifest = json.loads((_REPO_ROOT / "docs" / "BOX3_SEALED_MODEL_MANIFEST.json").read_text(encoding="utf-8"))
    manifest["model_digest"] = "sha256:" + "0" * 64
    with pytest.raises(V.VerifyError) as exc:
        V.validate_sealed_manifest(manifest)
    assert str(exc.value) == "MANIFEST_SCHEMA_INVALID"


def test_committed_manifest_is_schema_valid():
    manifest = json.loads((_REPO_ROOT / "docs" / "BOX3_SEALED_MODEL_MANIFEST.json").read_text(encoding="utf-8"))
    V.validate_sealed_manifest(manifest)  # 예외 없어야 한다
    assert manifest["model_role"] == "box3_draft"


def test_manifest_physical_rehash_matches(tmp_path):
    """manifest.model_digest 가 물리 파일 fd 기반 재해싱 결과와 일치한다(자기완결 fixture)."""
    model = tmp_path / "box3.gguf"
    model.write_bytes(b"SEALED-MODEL-BYTES" * 777)
    identity = hash_model_file_for_security(str(model))
    manifest = {
        "schema_version": "box3.sealed_model_manifest.v1",
        "model_role": "box3_draft",
        "model_name": "test-box3",
        "model_version": "vtest",
        "model_digest": identity.model_digest,
        "model_size_bytes": identity.size_bytes,
        "eval_summary_sha256": "sha256:" + "1" * 64,
        "eval_suite": "test.suite.v1",
        "sealed_at": "2026-07-09T00:00:00Z",
        "sealed_by_digest": "sha256:" + "2" * 64,
        "source_commit": "0" * 40,
    }
    V.validate_sealed_manifest(manifest)
    assert hash_model_file_for_security(str(model)).model_digest == manifest["model_digest"]


def test_verify_missing_model_is_meta_only_reason(tmp_path):
    """--model 이 없는 파일이어도 raw traceback/경로 노출 없이 고정 reason 으로 fail-closed."""
    manifest_path = _REPO_ROOT / "docs" / "BOX3_SEALED_MODEL_MANIFEST.json"
    approval = _valid_approval("sha256:" + "e" * 64)
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")
    approval_path.chmod(0o600)
    missing_model = tmp_path / "does_not_exist.gguf"
    with pytest.raises(V.VerifyError) as exc:
        V.verify(approval_path, manifest_path, missing_model, missing_model)
    # OSError 가 raw 로 새지 않고 고정 enum 으로 변환된다.
    assert str(exc.value) == "PHYSICAL_MODEL_DIGEST_MISMATCH"


def test_no_git_add_all_pollution_manifest():
    """git add -A 금지: 변경/신규 파일이 v1.2 허용 범위 밖으로 새지 않는다."""
    result = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "status", "--short"],
        capture_output=True,
        text=True,
        check=True,
    )
    allowed_prefixes = (
        "butler_pc_core/cards/box3/",
        "butler_pc_core/inference/model_identity.py",
        "scripts/generate_box3_model_scope_approval.py",
        "scripts/verify_box3_model_scope_approval.py",
        "scripts/cache_toctou_probe.py",
        "docs/BOX3_SEALED_MODEL_MANIFEST.json",
        "tests/cards/box3/",
        "tests/test_model_path_identity.py",
        "evidence/",
    )
    stray = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        path = parts[-1]
        if not any(path.startswith(pref) for pref in allowed_prefixes):
            stray.append(path)
    assert stray == [], f"허용 범위 밖 변경: {stray}"
