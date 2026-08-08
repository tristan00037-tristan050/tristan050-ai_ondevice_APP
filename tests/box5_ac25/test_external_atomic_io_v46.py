from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from scripts.ops import external_atomic_io as atomic


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "repository"
    evidence_root = tmp_path / "evidence"
    output_parent = evidence_root / "nested"
    repo_root.mkdir(mode=0o700)
    evidence_root.mkdir(mode=0o700)
    output_parent.mkdir(mode=0o700)
    return repo_root, evidence_root, output_parent


def write(
    roots: tuple[Path, Path, Path], payload: bytes = b"evidence\n"
) -> atomic.ExternalWriteResult:
    repo_root, evidence_root, output_parent = roots
    return atomic.write_external_bytes_atomic(
        repo_root=repo_root,
        evidence_root=evidence_root,
        output=output_parent / "result.bin",
        payload=payload,
        max_payload_bytes=1024,
    )


def assert_error(expected: str, operation) -> None:
    with pytest.raises(atomic.ExternalWriteError) as caught:
        operation()
    assert caught.value.code == expected


def test_atomic_write_returns_reopened_identity_and_exact_bytes(roots) -> None:
    payload = b"\x00bounded\nbytes\xff"
    result = write(roots, payload)
    output = roots[2] / "result.bin"
    observed = output.stat()
    assert output.read_bytes() == payload
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.byte_count == len(payload)
    assert (result.final_device, result.final_inode) == (
        observed.st_dev,
        observed.st_ino,
    )
    assert stat.S_IMODE(observed.st_mode) == 0o600
    assert observed.st_nlink == 1


def test_existing_regular_file_is_atomically_replaced(roots) -> None:
    output = roots[2] / "result.bin"
    output.write_bytes(b"old")
    output.chmod(0o600)
    before = output.stat().st_ino
    write(roots, b"new")
    assert output.read_bytes() == b"new"
    assert output.stat().st_ino != before


def test_payload_limit_is_enforced_before_creation(roots) -> None:
    repo_root, evidence_root, output_parent = roots
    output = output_parent / "result.bin"
    assert_error(
        "OUTPUT_PAYLOAD_TOO_LARGE",
        lambda: atomic.write_external_bytes_atomic(
            repo_root=repo_root,
            evidence_root=evidence_root,
            output=output,
            payload=b"12345",
            max_payload_bytes=4,
        ),
    )
    assert not output.exists()


def test_relative_output_is_rejected(roots) -> None:
    repo_root, evidence_root, _output_parent = roots
    assert_error(
        "OUTPUT_PATH_NOT_ABSOLUTE",
        lambda: atomic.write_external_bytes_atomic(
            repo_root=repo_root,
            evidence_root=evidence_root,
            output=Path("relative.bin"),
            payload=b"x",
            max_payload_bytes=1,
        ),
    )


def test_noncanonical_output_is_rejected(roots) -> None:
    repo_root, evidence_root, output_parent = roots
    output = Path(os.fspath(output_parent) + "/../nested/result.bin")
    assert_error(
        "OUTPUT_PATH_INVALID_COMPONENT",
        lambda: atomic.write_external_bytes_atomic(
            repo_root=repo_root,
            evidence_root=evidence_root,
            output=output,
            payload=b"x",
            max_payload_bytes=1,
        ),
    )


def test_output_outside_evidence_root_is_rejected(roots) -> None:
    repo_root, evidence_root, _output_parent = roots
    assert_error(
        "OUTPUT_PATH_OUTSIDE_EVIDENCE_ROOT",
        lambda: atomic.write_external_bytes_atomic(
            repo_root=repo_root,
            evidence_root=evidence_root,
            output=repo_root.parent / "elsewhere.bin",
            payload=b"x",
            max_payload_bytes=1,
        ),
    )


def test_evidence_root_inside_repository_is_rejected(tmp_path: Path) -> None:
    repo_root = tmp_path / "repository"
    evidence_root = repo_root / "evidence"
    repo_root.mkdir(mode=0o700)
    evidence_root.mkdir(mode=0o700)
    assert_error(
        "OUTPUT_PATH_INSIDE_REPOSITORY",
        lambda: atomic.write_external_bytes_atomic(
            repo_root=repo_root,
            evidence_root=evidence_root,
            output=evidence_root / "result.bin",
            payload=b"x",
            max_payload_bytes=1,
        ),
    )


def test_evidence_root_requires_exact_private_mode(roots) -> None:
    roots[1].chmod(0o750)
    assert_error("OUTPUT_ROOT_MODE_INVALID", lambda: write(roots))


def test_symlink_parent_component_is_rejected(roots) -> None:
    repo_root, evidence_root, output_parent = roots
    real_parent = evidence_root / "real"
    real_parent.mkdir(mode=0o700)
    linked_parent = evidence_root / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    assert_error(
        "OUTPUT_PATH_SYMLINK_COMPONENT",
        lambda: atomic.write_external_bytes_atomic(
            repo_root=repo_root,
            evidence_root=evidence_root,
            output=linked_parent / "result.bin",
            payload=b"x",
            max_payload_bytes=1,
        ),
    )
    assert not (real_parent / "result.bin").exists()


@pytest.mark.parametrize("unsafe_kind", ["directory", "fifo", "symlink"])
def test_unsafe_existing_destination_is_rejected(roots, unsafe_kind: str) -> None:
    output = roots[2] / "result.bin"
    if unsafe_kind == "directory":
        output.mkdir()
    elif unsafe_kind == "fifo":
        os.mkfifo(output)
    else:
        target = roots[2] / "target.bin"
        target.write_bytes(b"target")
        output.symlink_to(target)
    assert_error("OUTPUT_PATH_UNSAFE_TYPE", lambda: write(roots))


def test_hardlinked_existing_destination_is_rejected(roots) -> None:
    source = roots[2] / "source.bin"
    output = roots[2] / "result.bin"
    source.write_bytes(b"same inode")
    os.link(source, output)
    assert_error("OUTPUT_PATH_UNSAFE_TYPE", lambda: write(roots))


def test_root_replacement_detected_before_rename(roots, monkeypatch) -> None:
    original = atomic._revalidate_chain
    calls = 0

    def replaced(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise atomic.ExternalWriteError("OUTPUT_ROOT_REPLACED")
        return original(**kwargs)

    monkeypatch.setattr(atomic, "_revalidate_chain", replaced)
    assert_error("OUTPUT_ROOT_REPLACED", lambda: write(roots))
    assert not (roots[2] / "result.bin").exists()


def test_post_rename_destination_swap_is_detected(roots, monkeypatch) -> None:
    original_rename = atomic.os.rename
    monkeypatch.setattr(atomic, "_require_platform", lambda: None)

    def swap_after_rename(source, destination, **kwargs):
        original_rename(source, destination, **kwargs)
        parent_fd = kwargs["dst_dir_fd"]
        os.unlink(destination, dir_fd=parent_fd)
        swapped = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=parent_fd,
        )
        os.write(swapped, b"attacker")
        os.close(swapped)

    monkeypatch.setattr(atomic.os, "rename", swap_after_rename)
    assert_error("OUTPUT_REOPEN_MISMATCH", lambda: write(roots))
    assert not (roots[2] / "result.bin").exists()


def test_cli_is_meta_only_on_invalid_arguments(capsys) -> None:
    assert atomic.main(["--bogus", "secret-value"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        "EXTERNAL_BYTES_WRITTEN=0",
        "ERROR_CODE=OUTPUT_ARGUMENT_INVALID",
    ]
    assert "secret-value" not in captured.out
