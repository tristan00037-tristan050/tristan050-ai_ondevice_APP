from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.no_sidecar_token
ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts/build_complete_app.sh"


@pytest.mark.parametrize("value", ["", "true", "false", "yes", "2", " 1", "1 "])
def test_build_wrapper_rejects_invalid_distribution_flag_before_other_work(value: str) -> None:
    environment = os.environ.copy()
    environment["BUTLER_RELEASE_DISTRIBUTION"] = value
    completed = subprocess.run(
        ["bash", str(BUILD_SCRIPT)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 1
    assert "RELEASE_DISTRIBUTION_FLAG_INVALID" in completed.stdout
    assert "[0/5]" not in completed.stdout
