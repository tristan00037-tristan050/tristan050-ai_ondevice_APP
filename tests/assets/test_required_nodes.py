from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ROOT / "contracts/assets/required-test-nodes.txt"
pytestmark = pytest.mark.no_sidecar_token


def _function_has_skip(path: Path, function_name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != function_name:
            continue
        rendered = ast.dump(node, include_attributes=False)
        return "pytest.skip" in rendered or "pytest.mark.skip" in rendered
    return True


def test_no_required_asset_test_is_missing_or_skipped() -> None:
    required = [
        line.strip()
        for line in REQUIRED.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/assets"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, "REQUIRED_TEST_COLLECTION_FAILED"
    collected = set(completed.stdout.splitlines())
    assert [node for node in required if node not in collected] == []
    for node in required:
        relative, function_name = node.split("::", 1)
        assert not _function_has_skip(ROOT / relative, function_name), node
