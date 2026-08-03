from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verify_box5_authorization_audit import verify_ac11_schema_matrix


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "scripts/audit/reproduce_box5_ac11_schema_constraints_v1.py"


def _raw_matrix(tmp_path: Path) -> Path:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, str(RUNNER)],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert (result.returncode, result.stderr) == (0, "")
    path = tmp_path / "ac11-schema-matrix.env"
    path.write_text(result.stdout, encoding="ascii", newline="\n")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_raw_product_matrix_has_strict_valid_semantics(tmp_path: Path) -> None:
    matrix = _raw_matrix(tmp_path)
    result = verify_ac11_schema_matrix(matrix, _sha256(matrix))
    assert result == {
        "attack_count": 15,
        "matrix_sha256": _sha256(matrix),
        "normal_rows": 1,
        "weakened_rows": 0,
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda text: text.replace("ATTACK_01_ROWS=0\n", "", 1),
        lambda text: text + "ATTACK_01_ROWS=0\n",
        lambda text: text + "UNKNOWN_RESULT=TRUE\n",
        lambda text: text.replace(
            "AC11_SCHEMA_CONSTRAINT_MATRIX_PASS=TRUE",
            "AC11_SCHEMA_CONSTRAINT_MATRIX_PASS=FALSE",
        ),
        lambda text: text.replace(
            "ATTACK_15_SECOND=STORE_BLOCKED:AUTHORIZATION_REPLAY_SCHEMA_MISMATCH",
            "ATTACK_15_SECOND=REPLAY_BLOCKED",
        ),
    ],
)
def test_missing_duplicate_unknown_or_contradictory_matrix_is_blocked(
    tmp_path: Path, mutate
) -> None:
    matrix = _raw_matrix(tmp_path)
    matrix.write_text(mutate(matrix.read_text(encoding="ascii")), encoding="ascii")
    with pytest.raises(ValueError, match="AC11_SCHEMA_MATRIX_INVALID"):
        verify_ac11_schema_matrix(matrix, _sha256(matrix))


def test_matrix_hash_mismatch_is_blocked(tmp_path: Path) -> None:
    matrix = _raw_matrix(tmp_path)
    with pytest.raises(ValueError, match="AC11_SCHEMA_MATRIX_INVALID"):
        verify_ac11_schema_matrix(matrix, "0" * 64)
