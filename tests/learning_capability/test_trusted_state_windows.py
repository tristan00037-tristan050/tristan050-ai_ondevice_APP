from __future__ import annotations

import os
import subprocess
import getpass
from pathlib import Path

import pytest

from butler_pc_core.learning_capability.trusted_state_windows import (
    WindowsTrustedStateAdapter,
    WindowsTrustedStateError,
    validate_relative_name,
)


pytestmark = [
    pytest.mark.no_sidecar_token,
    pytest.mark.skipif(os.name != "nt", reason="windows-2025 only"),
]


def _adapter(tmp_path: Path) -> WindowsTrustedStateAdapter:
    scope = tmp_path / "trusted"
    scope.mkdir()
    return WindowsTrustedStateAdapter(scope)


def _write_private(path: Path) -> None:
    path.write_bytes(b'{"schema_version":2}')
    subprocess.run(
        ["icacls", str(path), "/inheritance:r"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["icacls", str(path), "/grant:r", f"{getpass.getuser()}:(F)"],
        check=True,
        capture_output=True,
    )


def test_windows_rejects_final_reparse_point(tmp_path):
    adapter = _adapter(tmp_path)
    target = tmp_path / "target.json"
    _write_private(target)
    link = adapter.scope / "state.json"
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.fail(f"windows-2025 symlink unavailable: {exc}")
    with pytest.raises(WindowsTrustedStateError, match="REPARSE_POINT_REJECTED"):
        adapter.read_verified("state.json", max_bytes=4096)


def test_windows_rejects_intermediate_reparse_point(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    _write_private(real / "state.json")
    scope = tmp_path / "junction"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(scope), str(real)],
        check=True,
        capture_output=True,
    )
    adapter = WindowsTrustedStateAdapter(scope)
    with pytest.raises(WindowsTrustedStateError, match="REPARSE_POINT_REJECTED"):
        adapter.read_verified("state.json", max_bytes=4096)


def test_windows_rejects_unc_device_namespace_and_ads(tmp_path):
    adapter = _adapter(tmp_path)
    for name in (
        r"\\server\share\state.json",
        r"\\?\C:\state.json",
        r"\\.\C:\state.json",
        r"C:state.json",
        r"state.json:ads",
        "NUL.txt",
        "state.json.",
    ):
        with pytest.raises(
            WindowsTrustedStateError, match="WINDOWS_NAMESPACE_REJECTED"
        ):
            validate_relative_name(name)
    assert adapter.scope.is_absolute()


def test_windows_rejects_dacl_writable_by_other_ordinary_users(tmp_path):
    adapter = _adapter(tmp_path)
    path = adapter.scope / "state.json"
    _write_private(path)
    subprocess.run(
        ["icacls", str(path), "/grant", "*S-1-1-0:(W)"],
        check=True,
        capture_output=True,
    )
    with pytest.raises(WindowsTrustedStateError, match="WINDOWS_DACL_UNTRUSTED"):
        adapter.read_verified("state.json", max_bytes=4096)


def test_windows_rejects_owner_sid_mismatch(tmp_path):
    adapter = _adapter(tmp_path)
    path = adapter.scope / "state.json"
    _write_private(path)
    changed = subprocess.run(
        ["icacls", str(path), "/setowner", "*S-1-5-32-544"],
        capture_output=True,
    )
    if changed.returncode != 0:
        pytest.fail("windows-2025 runner cannot exercise owner mismatch")
    with pytest.raises(WindowsTrustedStateError, match="WINDOWS_OWNER_MISMATCH"):
        adapter.read_verified("state.json", max_bytes=4096)


def test_windows_rejects_volume_or_file_id_change(tmp_path):
    adapter = _adapter(tmp_path)
    path = adapter.scope / "state.json"
    replacement = adapter.scope / "replacement.json"
    _write_private(path)
    _write_private(replacement)
    _, identity = adapter.read_verified("state.json", max_bytes=4096)
    os.replace(replacement, path)
    with pytest.raises(WindowsTrustedStateError, match="WINDOWS_FILE_ID_CHANGED"):
        adapter.assert_unchanged("state.json", identity)
