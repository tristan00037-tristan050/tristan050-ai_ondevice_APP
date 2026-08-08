from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.write_build_info import _A4_CODE_FILES, BuildInfoWriteError, write_build_info


pytestmark = pytest.mark.no_sidecar_token

_VALID = {
    "build_oid": "b" * 40,
    "build_tree_oid": "c" * 40,
    "git_describe": "v0.9.0-2-gbbbbbbb-dirty",
    "timestamp_utc": "2026-07-15T09:10:11Z",
    "app_version": "0.9.0",
}


def _prepare_a4_files(root: Path) -> None:
    for relative in _A4_CODE_FILES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((relative + "\n").encode("utf-8"))


def test_write_build_info_atomically_writes_exact_validated_payload(tmp_path):
    _prepare_a4_files(tmp_path)
    output = tmp_path / "BUILD_INFO.json"
    write_build_info(output, **_VALID)

    payload = json.loads(output.read_text(encoding="utf-8"))
    closure = payload.pop("a4_code_closure")
    helper = payload.pop("a4_authority_helper")
    box5 = payload.pop("box5_authority")
    distribution = payload.pop("distribution")
    assert closure["schema_version"] == "butler.a4.code_closure.v5.3"
    assert set(closure["files"]) == set(_A4_CODE_FILES)
    assert len(closure["digest"]) == 64
    assert helper == {"bundled": False, "sha256": None}
    assert box5 == {
        "bundled": False,
        "helper_identifier": None,
        "helper_sha256": None,
        "policy_sha256": None,
    }
    # 기본값은 내부 빌드다. 배포용이 아님이 명시적으로 남아야 한다.
    assert distribution == {
        "schema_version": "butler.build_info.distribution.v1",
        "release_distribution": False,
        "not_for_distribution": True,
        "root_anchor_sha256": None,
    }
    assert payload == {
        "app": "Butler",
        "app_version": "0.9.0",
        "build_base_commit_oid": "b" * 40,
        "build_tree_oid": "c" * 40,
        "build_timestamp_utc": "2026-07-15T09:10:11Z",
        "builder": "build_complete_app.sh",
        "git_describe": "v0.9.0-2-gbbbbbbb-dirty",
    }
    assert not list(tmp_path.glob(".BUILD_INFO.json.*.tmp"))


def test_write_build_info_binds_authority_helper_bytes(tmp_path):
    _prepare_a4_files(tmp_path)
    helper = tmp_path / "A4VerifierAuthority"
    helper.write_bytes(b"signed-authority-helper")
    output = tmp_path / "BUILD_INFO.json"
    write_build_info(output, authority_helper=helper, **_VALID)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["a4_authority_helper"] == {
        "bundled": True,
        "sha256": "f4b7215386e763c678a9ff707462de66d2011f192258c23eb21783e35b8a140a",
    }


def test_write_build_info_binds_box5_helper_and_policy_as_one_unit(tmp_path):
    _prepare_a4_files(tmp_path)
    authority = tmp_path / "box5"
    authority.mkdir()
    helper = authority / "Box5UserAuthority"
    policy = authority / "authorization-trust-policy-v2.json"
    helper.write_bytes(b"signed helper bytes")
    policy.write_bytes(b'{"schema_version":"2.0"}')
    output = tmp_path / "BUILD_INFO.json"
    write_build_info(
        output,
        box5_authority_helper=helper,
        box5_authority_policy=policy,
        **_VALID,
    )
    assert json.loads(output.read_text("utf-8"))["box5_authority"] == {
        "bundled": True,
        "helper_identifier": "com.butler.box5.user-authority.v2",
        "helper_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
        "policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
    }


def test_write_build_info_rejects_partial_box5_authority(tmp_path):
    _prepare_a4_files(tmp_path)
    helper = tmp_path / "Box5UserAuthority"
    helper.write_bytes(b"helper")
    with pytest.raises(BuildInfoWriteError, match="BOX5_AUTHORITY_BINDING_INCOMPLETE"):
        write_build_info(
            tmp_path / "BUILD_INFO.json",
            box5_authority_helper=helper,
            **_VALID,
        )


def test_distribution_build_records_bound_root_anchor(tmp_path):
    _prepare_a4_files(tmp_path)
    output = tmp_path / "BUILD_INFO.json"
    anchor = "a" * 64
    write_build_info(output, release_distribution=True, root_anchor=anchor, **_VALID)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["distribution"] == {
        "schema_version": "butler.build_info.distribution.v1",
        "release_distribution": True,
        "not_for_distribution": False,
        "root_anchor_sha256": anchor,
    }


def test_distribution_claim_without_root_anchor_is_rejected(tmp_path):
    _prepare_a4_files(tmp_path)
    with pytest.raises(BuildInfoWriteError, match="DISTRIBUTION_WITHOUT_ROOT_ANCHOR"):
        write_build_info(
            tmp_path / "BUILD_INFO.json", release_distribution=True, **_VALID
        )


@pytest.mark.parametrize("anchor", ["", "A" * 64, "a" * 63, "z" * 64])
def test_malformed_root_anchor_is_rejected(tmp_path, anchor):
    _prepare_a4_files(tmp_path)
    with pytest.raises(BuildInfoWriteError, match="INVALID_ROOT_ANCHOR"):
        write_build_info(tmp_path / "BUILD_INFO.json", root_anchor=anchor, **_VALID)


def test_internal_build_keeps_root_anchor_absent_rather_than_filled(tmp_path):
    """anchor 가 없으면 없는 것으로 남긴다 — 임의 값으로 채우지 않는다."""
    _prepare_a4_files(tmp_path)
    output = tmp_path / "BUILD_INFO.json"
    write_build_info(output, **_VALID)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["distribution"]["root_anchor_sha256"] is None
    assert payload["distribution"]["not_for_distribution"] is True


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        ({"build_oid": "unknown"}, "INVALID_BUILD_OID"),
        ({"build_tree_oid": "unknown"}, "INVALID_BUILD_TREE_OID"),
        ({"timestamp_utc": "2026-07-15"}, "INVALID_BUILD_TIMESTAMP"),
        ({"app_version": "unknown"}, "INVALID_APP_VERSION"),
    ],
)
def test_write_build_info_rejects_incomplete_provenance(
    tmp_path, overrides, error_code
):
    arguments = {**_VALID, **overrides}
    with pytest.raises(BuildInfoWriteError, match=error_code):
        write_build_info(tmp_path / "BUILD_INFO.json", **arguments)


def test_replace_failure_preserves_existing_stamp_and_cleans_temp(
    tmp_path, monkeypatch
):
    _prepare_a4_files(tmp_path)
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
            "--build-tree-oid",
            _VALID["build_tree_oid"],
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
