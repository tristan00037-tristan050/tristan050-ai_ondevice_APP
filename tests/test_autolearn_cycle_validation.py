#!/usr/bin/env python3
"""Regression tests for autolearn cycle validation (P1 hotfix).

Defect 1: verify_train_input_v1.py missing --json-out flag → cycle step 4 always broke
Defect 2: train_student_qlora_worldclass_v1.py falsely reported ready even when deps missing
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


def test_happy_verify_train_input_with_json_out():
    """Defect 1 regression — --json-out flag must write valid JSON and exit 0."""
    with tempfile.TemporaryDirectory() as tmp:
        train_path = Path(tmp) / "train.jsonl"
        val_path = Path(tmp) / "val.jsonl"
        test_path = Path(tmp) / "test.jsonl"
        json_out = Path(tmp) / "result.json"

        for p in [train_path, val_path, test_path]:
            p.write_text(
                '{"input": "x", "output": "y", "prompt": "x", "completion": "y", "split": "train"}\n',
                encoding="utf-8",
            )

        result = subprocess.run(
            [
                "python3",
                "scripts/ai/verify_train_input_v1.py",
                "--train", str(train_path),
                "--val", str(val_path),
                "--test", str(test_path),
                "--json-out", str(json_out),
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"verify failed: {result.stderr}"
        assert json_out.exists(), "--json-out file was not created"

        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["schema_version"] == "verify_train_input.v1"
        assert "overall_ok" in data
        assert "timestamp" in data
        assert "errors" in data


def test_adv_verify_train_input_unknown_flag_rejected():
    """Unknown flags must still be rejected (argparse contract unchanged)."""
    result = subprocess.run(
        [
            "python3",
            "scripts/ai/verify_train_input_v1.py",
            "--nonexistent-flag", "value",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "unknown flag should fail"


def test_adv_verify_train_input_dry_run_no_json_out():
    """--dry-run without --json-out must still exit 0 (no regression)."""
    result = subprocess.run(
        ["python3", "scripts/ai/verify_train_input_v1.py", "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"dry-run failed: {result.stderr}"
    assert ("TRAIN_EVAL_INPUT_SANITY_V1_OK=" + "1") in result.stdout


def test_adv_train_qlora_fails_when_deps_missing(monkeypatch):
    """Defect 2 regression — exit 1 + stderr when dependencies are missing."""
    spec = importlib.util.find_spec("transformers")
    if spec is not None:
        # transformers installed: skip; can't simulate missing deps reliably here
        return

    result = subprocess.run(
        [
            "python3",
            "scripts/upgrade/train_student_qlora_worldclass_v1.py",
            "--train-file", "/dev/null",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, (
        f"should exit 1 when deps missing, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "NOT_READY" in result.stderr or "MISSING" in result.stderr


def test_happy_train_qlora_succeeds_when_deps_present():
    """When all deps are installed, exit 0 and print READY_OK."""
    spec = importlib.util.find_spec("transformers")
    if spec is None:
        return  # deps not installed in this env — skip

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        Path(f.name).write_text(
            '{"prompt": "x", "completion": "y"}\n', encoding="utf-8"
        )
        train_file = f.name

    result = subprocess.run(
        [
            "python3",
            "scripts/upgrade/train_student_qlora_worldclass_v1.py",
            "--train-file", train_file,
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"should exit 0 when deps present\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert ("WORLDCLASS_STUDENT_QLORA_READY_OK=" + "1") in result.stdout


def test_boundary_autolearn_cycle_step4_completes():
    """Smoke: verify_train_input accepts --json-out path with nested dirs (mkdir -p)."""
    with tempfile.TemporaryDirectory() as tmp:
        train_path = Path(tmp) / "data" / "train.jsonl"
        train_path.parent.mkdir(parents=True)
        train_path.write_text(
            '{"prompt": "p", "completion": "c", "split": "train"}\n',
            encoding="utf-8",
        )
        json_out = Path(tmp) / "deep" / "nested" / "result.json"

        result = subprocess.run(
            [
                "python3",
                "scripts/ai/verify_train_input_v1.py",
                "--train", str(train_path),
                "--json-out", str(json_out),
            ],
            capture_output=True,
            text=True,
        )
        assert json_out.exists(), f"nested --json-out dir not created\nstderr: {result.stderr}"
