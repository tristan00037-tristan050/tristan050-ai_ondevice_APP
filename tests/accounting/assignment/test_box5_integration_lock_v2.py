from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.verify_box5_integration_lock as integration_verifier


ROOT = Path(__file__).resolve().parents[3]


def _forged_lock(tmp_path: Path, mutate) -> Path:
    lock = json.loads((ROOT / "integration_lock.json").read_text(encoding="utf-8"))
    mutate(lock)
    path = tmp_path / "integration_lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")
    return path


def test_lock_rejects_omitted_critical_source(tmp_path, monkeypatch) -> None:
    def omit(lock):
        lock["critical_files"].pop("butler_pc_core/accounting/assignment/authorization.py")

    monkeypatch.setattr(integration_verifier, "LOCK_PATH", _forged_lock(tmp_path, omit))
    with pytest.raises(RuntimeError, match="CRITICAL_PATH_SET_MISMATCH"):
        integration_verifier.verify(allow_worktree_base=True)


def test_lock_rejects_forged_blob_identity(tmp_path, monkeypatch) -> None:
    def forge(lock):
        lock["critical_files"]["butler_pc_core/accounting/assignment/runtime.py"][
            "blob_oid"
        ] = "0" * 40

    monkeypatch.setattr(integration_verifier, "LOCK_PATH", _forged_lock(tmp_path, forge))
    with pytest.raises(RuntimeError, match="CRITICAL_FILE_IDENTITY_MISMATCH"):
        integration_verifier.verify(allow_worktree_base=True)


def test_lock_rejects_submitter_wildcard_allowlist(tmp_path, monkeypatch) -> None:
    def broaden(lock):
        lock["allowed_paths"] = ["**"]

    monkeypatch.setattr(integration_verifier, "LOCK_PATH", _forged_lock(tmp_path, broaden))
    with pytest.raises(RuntimeError, match="ALLOWED_PATHS_INVALID"):
        integration_verifier.verify(allow_worktree_base=True)
