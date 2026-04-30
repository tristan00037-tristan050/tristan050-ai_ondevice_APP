"""Regression tests for autolearn cycle validation (P1 hotfix).

Defect 1: verify_train_input_v1.py missing --json-out flag broke cycle step 4
Defect 2: train_student_qlora_worldclass_v1.py falsely reported ready even when deps missing
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "ai" / "verify_train_input_v1.py"
QLORA_SCRIPT = REPO_ROOT / "scripts" / "upgrade" / "train_student_qlora_worldclass_v1.py"
CYCLE_SCRIPT = REPO_ROOT / "scripts" / "upgrade" / "run_continual_autolearn_cycle_v1.py"


def _sample_jsonl_row() -> str:
    return '{"prompt": "q", "completion": "a", "split": "train"}\n'


# ─── Defect 1: --json-out ────────────────────────────────────────────────────


def test_happy_verify_train_input_with_json_out():
    """Defect 1 regression — --json-out writes valid JSON and exits 0."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        train = tmp / "train.jsonl"
        val = tmp / "val.jsonl"
        test_f = tmp / "test.jsonl"
        json_out = tmp / "result.json"

        for p in (train, val, test_f):
            p.write_text(_sample_jsonl_row(), encoding="utf-8")

        proc = subprocess.run(
            [
                sys.executable, str(VERIFY_SCRIPT),
                "--train", str(train),
                "--val", str(val),
                "--test", str(test_f),
                "--json-out", str(json_out),
            ],
            capture_output=True, text=True,
        )

        assert proc.returncode == 0, f"exit {proc.returncode}: {proc.stderr}"
        assert json_out.exists(), "--json-out file was not created"

        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["schema_version"] == "verify_train_input.v1"
        assert "overall_ok" in data
        assert "train" in data and "val" in data and "test" in data
        assert data["overall_ok"] is True
        assert isinstance(data["errors"], list)


def test_adv_verify_train_input_unknown_flag_rejected():
    """argparse must reject unknown flags (contract unchanged by hotfix)."""
    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--nonexistent-flag", "value"],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0, "unknown flag must be rejected"


def test_adv_verify_train_input_dry_run_exits_zero():
    """--dry-run exits 0 without requiring --train (no regression)."""
    proc = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--dry-run"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"dry-run failed: {proc.stderr}"


def test_boundary_json_out_creates_parent_dirs():
    """--json-out must create nested parent dirs automatically."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        train = tmp / "train.jsonl"
        train.write_text(_sample_jsonl_row(), encoding="utf-8")
        nested_out = tmp / "deep" / "nested" / "result.json"

        proc = subprocess.run(
            [
                sys.executable, str(VERIFY_SCRIPT),
                "--train", str(train),
                "--json-out", str(nested_out),
            ],
            capture_output=True, text=True,
        )
        assert nested_out.exists(), (
            f"nested dirs not created; exit={proc.returncode} err={proc.stderr}"
        )


# ─── Defect 2: promotion gate ────────────────────────────────────────────────


def _qlora_required_pkgs() -> list[str]:
    return ["transformers", "peft", "bitsandbytes", "trl", "datasets", "accelerate"]


def _missing_qlora_pkgs() -> list[str]:
    return [p for p in _qlora_required_pkgs() if importlib.util.find_spec(p) is None]


def test_adv_train_qlora_exits_one_when_deps_missing():
    """Defect 2 regression — exit 1 + MISSING_DEPENDENCIES JSON when deps absent."""
    missing = _missing_qlora_pkgs()
    if not missing:
        pytest.skip("all qlora deps present; cannot simulate missing-dep scenario")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        dummy_train = tmp_path / "train.jsonl"
        dummy_train.write_text(_sample_jsonl_row(), encoding="utf-8")
        out_json = tmp_path / "manifest.json"

        proc = subprocess.run(
            [
                sys.executable, str(QLORA_SCRIPT),
                "--train-file", str(dummy_train),
                "--out", str(out_json),
                "--dry-run",
            ],
            capture_output=True, text=True,
        )

        # Exit code must be 1 (not 0 silently passing)
        assert proc.returncode == 1, (
            f"should exit 1 when deps missing; got {proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )

        # JSON manifest must reflect failure
        assert out_json.exists(), "manifest not written on failure"
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert data.get("status") == "MISSING_DEPENDENCIES"
        assert data.get("ready") is False
        assert isinstance(data.get("missing_packages"), list)
        assert len(data["missing_packages"]) > 0


def test_happy_train_qlora_exits_zero_when_deps_present():
    """All deps installed → exit 0 + ready=True in manifest."""
    missing = _missing_qlora_pkgs()
    if missing:
        pytest.skip(f"deps not installed, cannot run happy-path: {missing}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        dummy_train = tmp_path / "train.jsonl"
        dummy_train.write_text(_sample_jsonl_row(), encoding="utf-8")
        out_json = tmp_path / "manifest.json"

        proc = subprocess.run(
            [
                sys.executable, str(QLORA_SCRIPT),
                "--train-file", str(dummy_train),
                "--out", str(out_json),
                "--dry-run",
            ],
            capture_output=True, text=True,
        )

        assert proc.returncode == 0, (
            f"deps present but failed; stderr={proc.stderr}"
        )
        assert out_json.exists(), "manifest not written on success"
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert data.get("ready") is True
        assert data.get("status") == "READY"


# ─── Cycle integration boundary ──────────────────────────────────────────────


def test_boundary_cycle_verify_flags_are_defined():
    """Flags passed by autolearn cycle to verify_train_input_v1.py must all be defined."""
    if not CYCLE_SCRIPT.exists():
        pytest.skip("run_continual_autolearn_cycle_v1.py not yet on this branch")

    cycle_text = CYCLE_SCRIPT.read_text(encoding="utf-8")
    verify_text = VERIFY_SCRIPT.read_text(encoding="utf-8")

    # Extract flags the cycle passes to verify_train_input
    call_block_match = re.search(
        r"verify_train_input_v1\.py.*?\]", cycle_text, re.DOTALL
    )
    used_flags: set[str] = set()
    if call_block_match:
        used_flags = set(re.findall(r"'(--[a-z][a-z\-]*)'", call_block_match.group(0)))

    # Extract flags defined in verify script's argparse
    defined_flags = set(re.findall(r"add_argument\(\s*['\"](-{1,2}[a-z][a-z\-]*)['\"]", verify_text))

    unknown = used_flags - defined_flags
    assert not unknown, (
        f"cycle passes undefined flags to verify_train_input_v1.py: {unknown}\n"
        f"defined: {defined_flags}"
    )
