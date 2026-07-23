"""test_cli.py — cli.py 진입점 경로·실행 검증."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def test_cli_help_returncode_zero():
    """python -m butler_pc_core.accounting.cli --help → returncode 0."""
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-m", "butler_pc_core.accounting.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=3,
    )
    elapsed = time.monotonic() - started
    assert result.returncode == 0, (
        f"returncode={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "usage" in result.stdout.lower() or "input" in result.stdout.lower(), (
        f"사용법 텍스트 없음: {result.stdout!r}"
    )
    assert elapsed < 2.0, f"CLI help startup exceeded budget: {elapsed:.3f}s"


def test_cli_help_does_not_import_product_dependency_graph():
    script = """
import importlib.abc
import runpy
import sys

class RejectHeavyImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.', 1)[0] in {'pandas', 'openpyxl', 'jsonschema'}:
            raise RuntimeError('heavy import attempted: ' + fullname)
        return None

sys.meta_path.insert(0, RejectHeavyImports())
sys.argv = ['butler-accounting', '--help']
runpy.run_module('butler_pc_core.accounting.cli', run_name='__main__')
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout
