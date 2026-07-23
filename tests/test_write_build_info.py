from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.write_build_info import BuildInfoWriteError, write_build_info

pytestmark = pytest.mark.no_sidecar_token

_VALID = {
    "build_oid": "b" * 40,
    "tree_oid": "c" * 40,
    "git_describe": "v0.9.0-2-gbbbbbbb-dirty",
    "timestamp_utc": "2026-07-15T09:10:11Z",
    "app_version": "0.9.0",
}


def test_write_build_info_atomically_writes_exact_validated_payload(tmp_path):
    output = tmp_path / "BUILD_INFO.json"
    write_build_info(output, **_VALID)

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "app": "Butler",
        "app_version": "0.9.0",
        "build_base_commit_oid": "b" * 40,
        "build_tree_oid": "c" * 40,
        "build_timestamp_utc": "2026-07-15T09:10:11Z",
        "builder": "build_complete_app.sh",
        "git_describe": "v0.9.0-2-gbbbbbbb-dirty",
    }
    assert not list(tmp_path.glob(".BUILD_INFO.json.*.tmp"))


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"build_oid": "unknown"}, "INVALID_BUILD_OID"),
        ({"tree_oid": "unknown"}, "INVALID_TREE_OID"),
        ({"timestamp_utc": "2026-07-15"}, "INVALID_BUILD_TIMESTAMP"),
        ({"app_version": "unknown"}, "INVALID_APP_VERSION"),
    ],
)
def test_write_build_info_rejects_incomplete_provenance(tmp_path, overrides, error_code):
    arguments = {**_VALID, **overrides}
    with pytest.raises(BuildInfoWriteError, match=error_code):
        write_build_info(tmp_path / "BUILD_INFO.json", **arguments)


def test_replace_failure_preserves_existing_stamp_and_cleans_temp(tmp_path, monkeypatch):
    output = tmp_path / "BUILD_INFO.json"
    previous = {"build_base_commit_oid": "previous"}
    output.write_text(json.dumps(previous), encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr("scripts.write_build_info.os.replace", fail_replace)
    with pytest.raises(BuildInfoWriteError, match="BUILD_INFO_WRITE_FAILED"):
        write_build_info(output, **_VALID)

    assert json.loads(output.read_text(encoding="utf-8")) == previous
    assert not list(tmp_path.glob(".BUILD_INFO.json.*.tmp"))


def test_cli_returns_nonzero_and_stable_code_when_stamp_cannot_be_written(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "write_build_info.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--output",
            str(tmp_path / "missing" / "BUILD_INFO.json"),
            "--build-oid",
            _VALID["build_oid"],
            "--tree-oid",
            _VALID["tree_oid"],
            "--git-describe",
            _VALID["git_describe"],
            "--timestamp-utc",
            _VALID["timestamp_utc"],
            "--app-version",
            _VALID["app_version"],
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 1
    assert completed.stdout.strip() == (
        "BUILD_INFO_WRITE_OK=0 ERROR_CODE=BUILD_INFO_PARENT_MISSING"
    )
    assert completed.stderr == ""


def test_source_archive_builder_identity_is_explicit(tmp_path):
    output = tmp_path / "BUILD_INFO.json"
    write_build_info(output, **_VALID, builder="build_safe_source_archive.py")
    assert json.loads(output.read_text(encoding="utf-8"))["builder"] == "build_safe_source_archive.py"


def test_write_build_info_rejects_control_characters(tmp_path):
    with pytest.raises(BuildInfoWriteError, match="INVALID_APP_VERSION"):
        write_build_info(
            tmp_path / "BUILD_INFO.json",
            **{**_VALID, "app_version": "0.9.0\nforged"},
        )
