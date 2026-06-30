from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts/verify_integrated_learning_contract.py"
SUCCESS_MARKER = "INTEGRATED_LEARNING_CONTRACT_" + "OK" + "=" + "1"
FAILURE_MARKER = "INTEGRATED_LEARNING_CONTRACT_" + "OK" + "=" + "0"


@pytest.mark.no_sidecar_token
def test_integrated_learning_verifier_success_emits_binary_ok():
    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), str(REPO_ROOT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == SUCCESS_MARKER


@pytest.mark.no_sidecar_token
def test_integrated_learning_verifier_failure_uses_fixed_codes(tmp_path):
    schema_dir = tmp_path / "schemas" / "learning"
    schema_dir.mkdir(parents=True)
    (schema_dir / "integrated_learning_candidate_v1.schema.json").write_text("{", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert FAILURE_MARKER in result.stdout
    assert "ERROR_CODE=SCHEMA_JSON_INVALID" in result.stdout
    assert "ERROR_CODE=JSON_PARSE_FAILED" in result.stdout
    assert "BLOCK:" not in result.stdout
    assert str(tmp_path) not in result.stdout
    assert "Expecting" not in result.stdout
