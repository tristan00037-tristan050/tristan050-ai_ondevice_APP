from __future__ import annotations

import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from butler_pc_core.assets.context import parse_platform_context
from butler_pc_core.assets.dev_sidecar import _bootstrap_frame


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.no_sidecar_token


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.mark.skipif(os.name != "posix", reason="descriptor bootstrap is POSIX-only")
def test_development_launcher_frame_is_native_and_unverified(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    asset_root.mkdir(mode=0o700)
    descriptor = os.open(
        asset_root,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        frame = _bootstrap_frame(
            app_data=tmp_path,
            asset_root_fd=descriptor,
            repository_root=ROOT,
        )
        (size,) = struct.unpack(">I", frame[:4])
        assert size == len(frame[4:])
        context = parse_platform_context(frame[4:], native_authority=True)
    finally:
        os.close(descriptor)
    assert context.asset_root_fd is not None
    assert context.native_authority is True
    assert context.manifest_set_sha256 is None
    assert context.trust_root_status == "TRUST_ROOT_NOT_CONFIGURED"
    assert context.bootstrap_security_state == {
        "auto_update_allowed": 0,
        "byte_safety_verified": False,
        "external_handoff_allowed": 0,
        "operation_scope": "INTERNAL_OWNER_ONLY",
        "origin_verified": False,
        "provenance_state": "UNVERIFIED",
        "release_ready": False,
        "signature_state": "MISSING",
        "trust_root_state": "UNCONFIGURED",
    }


def test_playwright_and_documented_launcher_use_descriptor_bootstrap() -> None:
    command = "python3 -m butler_pc_core.assets.dev_sidecar"
    assert command in (ROOT / "butler-desktop/playwright.config.ts").read_text(
        encoding="utf-8"
    )
    assert command in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    build_script = (ROOT / "scripts/build_complete_app.sh").read_text(
        encoding="utf-8"
    )
    assert "ASSET_STAGE_SKIPPED" not in build_script
    assert "ASSET_INVENTORY_NOT_PROVIDED" not in build_script


@pytest.mark.skipif(os.name != "posix", reason="descriptor bootstrap is POSIX-only")
def test_direct_sidecar_without_bootstrap_stays_fail_closed() -> None:
    environment = os.environ.copy()
    environment.pop("BUTLER_BOOTSTRAP_FD", None)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "butler_sidecar.py"),
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode != 0
    assert completed.stderr.rstrip().endswith("ASSET_BOOTSTRAP_FAILED")
    assert completed.stdout == ""


@pytest.mark.skipif(os.name != "posix", reason="descriptor bootstrap is POSIX-only")
def test_development_launcher_serves_real_sidecar_health(tmp_path: Path) -> None:
    port = _free_port()
    environment = os.environ.copy()
    environment["BUTLER_APP_DATA_DIR"] = str(tmp_path)
    environment["BUTLER_HOME_BOOTSTRAP_NEW_INSTALL"] = "1"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "butler_pc_core.assets.dev_sidecar",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("DEVELOPMENT_SIDECAR_EXITED")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health",
                    timeout=1,
                ) as response:
                    assert response.status == 200
                    assert isinstance(json.loads(response.read()), dict)
                    break
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        else:
            pytest.fail("DEVELOPMENT_SIDECAR_HEALTH_TIMEOUT")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
