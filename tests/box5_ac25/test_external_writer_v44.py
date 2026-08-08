from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
WRITER_PATH = ROOT / "scripts/ops/write_external_json_atomic.py"
GENERATOR = ROOT / "scripts/ops/gen_artifact_chain_proof_v2.sh"
SPEC = importlib.util.spec_from_file_location("ac25_external_writer", WRITER_PATH)
assert SPEC and SPEC.loader
writer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = writer
SPEC.loader.exec_module(writer)


def _call(repo: Path, evidence: Path, output: Path, payload=b"{}\n"):
    return writer.write_external_json_atomic(
        repo_root=repo, evidence_root=evidence, output=output, payload=payload,
    )


def _repo_and_evidence(tmp_path: Path):
    repo = tmp_path / "repo"
    evidence = tmp_path / "evidence"
    repo.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    return repo, evidence


def test_output_argument_required():
    result = subprocess.run(["bash", str(GENERATOR)], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode != 0
    assert result.stdout.splitlines() == ["ERROR_CODE=OUTPUT_PATH_REQUIRED"]


def test_relative_output_rejected(tmp_path):
    repo, evidence = _repo_and_evidence(tmp_path)
    with pytest.raises(writer.ExternalWriteError, match="OUTPUT_PATH_NOT_ABSOLUTE"):
        _call(repo, evidence, Path("relative.json"))


def test_output_inside_repo_rejected(tmp_path):
    repo = tmp_path / "repo"
    evidence = repo / "evidence"
    evidence.mkdir(parents=True)
    with pytest.raises(writer.ExternalWriteError, match="OUTPUT_PATH_INSIDE_REPOSITORY"):
        _call(repo, evidence, evidence / "proof.json")


def test_output_outside_evidence_root_rejected(tmp_path):
    repo, evidence = _repo_and_evidence(tmp_path)
    with pytest.raises(writer.ExternalWriteError, match="OUTPUT_PATH_OUTSIDE_EVIDENCE_ROOT"):
        _call(repo, evidence, tmp_path / "other.json")


def test_symlinked_parent_rejected(tmp_path):
    repo, evidence = _repo_and_evidence(tmp_path)
    real = evidence / "real"
    real.mkdir()
    (evidence / "link").symlink_to(real, target_is_directory=True)
    with pytest.raises(writer.ExternalWriteError, match="OUTPUT_PATH_SYMLINK_COMPONENT"):
        _call(repo, evidence, evidence / "link/proof.json")


def test_parent_swap_race_fails_closed(tmp_path, monkeypatch):
    repo, evidence = _repo_and_evidence(tmp_path)
    parent = evidence / "parent"
    parent.mkdir()
    original_replace = writer.os.replace

    def swap_then_replace(*args, **kwargs):
        moved = evidence / "moved"
        parent.rename(moved)
        parent.mkdir()
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(writer.os, "replace", swap_then_replace)
    with pytest.raises(writer.ExternalWriteError, match="OUTPUT_PATH_SYMLINK_COMPONENT"):
        _call(repo, evidence, parent / "proof.json")
    assert not (evidence / "moved/proof.json").exists()
    assert not (parent / "proof.json").exists()


def test_symlink_output_rejected(tmp_path):
    repo, evidence = _repo_and_evidence(tmp_path)
    target = evidence / "target"
    target.write_text("x")
    output = evidence / "proof.json"
    output.symlink_to(target)
    with pytest.raises(writer.ExternalWriteError, match="OUTPUT_PATH_UNSAFE_TYPE"):
        _call(repo, evidence, output)


def test_fifo_and_device_rejected(tmp_path):
    repo, evidence = _repo_and_evidence(tmp_path)
    output = evidence / "proof.json"
    os.mkfifo(output)
    assert stat.S_ISFIFO(output.lstat().st_mode)
    with pytest.raises(writer.ExternalWriteError, match="OUTPUT_PATH_UNSAFE_TYPE"):
        _call(repo, evidence, output)


def test_atomic_writer_reports_reopened_digest_and_size(tmp_path):
    repo, evidence = _repo_and_evidence(tmp_path)
    raw = b'{"ok":true}\n'
    result = _call(repo, evidence, evidence / "proof.json", raw)
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert result.byte_count == len(raw)
    assert (evidence / "proof.json").read_bytes() == raw
    assert stat.S_IMODE((evidence / "proof.json").stat().st_mode) == 0o600


def test_generator_leaves_worktree_byte_identical(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir(mode=0o700)
    before = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=ROOT,
    )
    env = {**os.environ, "AC25_EVIDENCE_ROOT": str(evidence)}
    result = subprocess.run(
        ["bash", str(GENERATOR), "--output", str(evidence / "proof.json")],
        cwd=ROOT, env=env, text=True, capture_output=True,
    )
    after = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=ROOT,
    )
    assert result.returncode == 0
    assert before == after


def test_all_call_sites_supply_external_output():
    results = subprocess.check_output(
        ["rg", "-l", "bash scripts/ops/gen_artifact_chain_proof_v2\\.sh", ".github", "scripts"],
        cwd=ROOT, text=True,
    ).splitlines()
    for relative in results:
        if relative.endswith("gen_artifact_chain_proof_v2.sh"):
            continue
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "--output" in source
        assert "AC25_EVIDENCE_ROOT" in source
