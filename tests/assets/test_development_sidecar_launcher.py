from __future__ import annotations

import hashlib
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
from butler_pc_core.assets.dev_sidecar import (
    _bootstrap_frame,
    _child_environment,
    _open_listener,
    _validate_listener,
)


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.no_sidecar_token


def _exit_code(stderr: str) -> str:
    if "Address already in use" in stderr or "address already in use" in stderr:
        return "SIDECAR_BIND_CONFLICT"
    if "ASSET_BOOTSTRAP_FAILED" in stderr:
        return "SIDECAR_ASSET_BOOTSTRAP_FAILED"
    if "HOME_STORAGE_" in stderr or "HOME_NEW_INSTALL_" in stderr:
        return "SIDECAR_HOME_STORAGE_FAILED"
    if "Application startup failed" in stderr:
        return "SIDECAR_STARTUP_FAILED"
    return "SIDECAR_UNKNOWN_EXIT"


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


def test_development_child_home_is_private_and_platform_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    linux_environment = _child_environment(app_data=tmp_path, bootstrap_fd=17)
    assert linux_environment["HOME"] == str(tmp_path)

    monkeypatch.setattr(sys, "platform", "darwin")
    macos_environment = _child_environment(app_data=tmp_path, bootstrap_fd=17)
    assert macos_environment["HOME"] == os.environ.get("HOME", str(Path.home()))
    assert macos_environment["BUTLER_APP_DATA_DIR"] == str(tmp_path)
    assert macos_environment["BUTLER_PRODUCTION"] == "0"


@pytest.mark.skipif(os.name != "posix", reason="descriptor bootstrap is POSIX-only")
def test_development_listener_validation_is_descriptor_bound() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])
        _validate_listener(listener.fileno(), host="127.0.0.1", port=port)
        with pytest.raises(SystemExit, match="BLOCK_DEVELOPMENT_LISTENER_MISMATCH"):
            _validate_listener(
                listener.fileno(),
                host="127.0.0.1",
                port=port + 1,
            )


@pytest.mark.skipif(os.name != "posix", reason="descriptor bootstrap is POSIX-only")
def test_development_listener_opens_loopback_before_sidecar_exec() -> None:
    descriptor = _open_listener(host="127.0.0.1", port=0)
    try:
        listener = socket.socket(fileno=os.dup(descriptor))
        try:
            assert listener.getsockname()[0] == "127.0.0.1"
            assert listener.getsockname()[1] > 0
        finally:
            listener.close()
    finally:
        os.close(descriptor)
    with pytest.raises(
        SystemExit,
        match="BLOCK_DEVELOPMENT_LISTEN_ADDRESS_INVALID",
    ):
        _open_listener(host="0.0.0.0", port=8765)


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
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(2048)
    port = int(listener.getsockname()[1])
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
            "--listen-fd",
            str(listener.fileno()),
        ],
        cwd=ROOT,
        env=environment,
        pass_fds=(listener.fileno(),),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    listener.close()
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr is not None else ""
                digest = hashlib.sha256(stderr.encode("utf-8")).hexdigest()
                pytest.fail(
                    "DEVELOPMENT_SIDECAR_EXITED "
                    f"error_code={_exit_code(stderr)} "
                    f"stderr_length={len(stderr.encode('utf-8'))} "
                    f"stderr_sha256={digest}"
                )
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
