from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.no_sidecar_token


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS native launcher contract")
def test_native_launcher_clears_poisoned_parent_environment() -> None:
    completed = subprocess.run(
        [
            "cargo",
            "test",
            "--locked",
            "--manifest-path",
            "butler-desktop/src-tauri/Cargo.toml",
            "native_launcher_clears_poisoned_parent_environment",
            "--",
            "--nocapture",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, "NATIVE_LAUNCHER_ENV_ISOLATION_FAILED"
    assert "1 passed" in completed.stdout
