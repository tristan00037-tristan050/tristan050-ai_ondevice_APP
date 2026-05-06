"""test_cli.py — cli.py 진입점 경로·실행 검증."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_cli_help_returncode_zero():
    """python -m butler_pc_core.accounting.cli --help → returncode 0."""
    result = subprocess.run(
        [sys.executable, "-m", "butler_pc_core.accounting.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"returncode={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "usage" in result.stdout.lower() or "input" in result.stdout.lower(), (
        f"사용법 텍스트 없음: {result.stdout!r}"
    )
