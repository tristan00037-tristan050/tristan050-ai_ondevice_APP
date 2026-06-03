from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_admin_policy_format_v1_2.sh"


def _run_verifier(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_verify_admin_policy_format_success_output_is_zero_one_only():
    result = _run_verifier(ROOT)

    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines
    assert all(re.fullmatch(r"[A-Z0-9_]+=1", line) for line in lines)
    assert "true" not in result.stdout.lower()
    assert "false" not in result.stdout.lower()


def test_verify_admin_policy_format_failure_output_is_redacted(tmp_path):
    target = tmp_path / "butler_pc_core" / "company_policy"
    target.mkdir(parents=True)
    forbidden_call = "console" + ".log(" + "\"to" + "ken\")\n"
    (target / "bad.py").write_text(forbidden_call, encoding="utf-8")

    result = _run_verifier(tmp_path)

    assert result.returncode == 1
    assert "TOKEN_STORAGE_LOG_ZERO=0" in result.stdout
    assert "BLOCK_TOKEN_STORAGE_OR_LOG" in result.stdout
    assert str(tmp_path) not in result.stdout
    assert "bad.py" not in result.stdout
    assert ("console" + ".log") not in result.stdout
    assert ("local" + "Storage") not in result.stdout
