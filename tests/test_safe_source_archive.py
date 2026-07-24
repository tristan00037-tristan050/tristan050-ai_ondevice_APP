from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.release import verify_source_bundle
from scripts.release.firstscreen_source_contracts import PROTECTED_PATHS, protected_contract_digest

pytestmark = pytest.mark.no_sidecar_token


def _success_verdict(key: str) -> str:
    return f"{key}_OK={int(True)}"


def _verify(
    root: Path,
    *,
    archive: Path,
    manifest: Path,
    source_root: Path | None = None,
    extract_to: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    source_argument = ["--source-root", str(source_root)] if source_root else ["--extract-to", str(extract_to)]
    return subprocess.run(
        [
            sys.executable,
            "scripts/release/verify_source_bundle.py",
            *source_argument,
            "--manifest",
            str(manifest),
            "--archive",
            str(archive),
            "--expected-manifest-sha256",
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


def _rewrite_entry(source: Path, destination: Path, name: str, payload: bytes) -> None:
    with zipfile.ZipFile(source) as archive:
        entries = [(copy.copy(info), archive.read(info)) for info in archive.infolist()]
    with zipfile.ZipFile(destination, "w") as archive:
        for info, current in entries:
            archive.writestr(info, payload if info.filename == name else current)


def test_safe_source_archive_is_byte_bound_and_self_reproducing_without_git(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "source.zip"
    manifest = tmp_path / "SOURCE_ARCHIVE_MANIFEST.json"
    build = subprocess.run(
        [
            sys.executable,
            "scripts/release/build_safe_source_archive.py",
            "--commit",
            "HEAD",
            "--scope-baseline",
            "HEAD^",
            "--output",
            str(output),
            "--manifest",
            str(manifest),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert build.returncode == 0, build.stdout

    unpacked = tmp_path / "unpacked"
    verification = _verify(root, archive=output, manifest=manifest, extract_to=unpacked)
    assert verification.returncode == 0, verification.stdout
    assert verification.stdout.strip() == _success_verdict("SOURCE_BUNDLE_VERIFY")
    assert not (unpacked / "source/.git").exists()
    no_git_verification = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/release/verify_source_bundle.py"),
            "--source-root",
            str(unpacked / "source"),
            "--manifest",
            str(manifest),
            "--archive",
            str(output),
            "--expected-manifest-sha256",
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
        ],
        cwd=unpacked / "source",
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert no_git_verification.returncode == 0, no_git_verification.stdout
    assert no_git_verification.stdout.strip() == _success_verdict("SOURCE_BUNDLE_VERIFY")
    stamp = json.loads((unpacked / "source/BUILD_INFO.json").read_text(encoding="utf-8"))
    declared = json.loads(manifest.read_text(encoding="utf-8"))
    assert declared["portable_path_policy"] == "NFC_CASEFOLD_WINDOWS_V1"
    assert declared["protected_scope"]["verified_unchanged"] is True
    assert declared["protected_scope"]["protected_paths"] == list(PROTECTED_PATHS)
    assert declared["protected_scope"]["contract_digest"] == protected_contract_digest()
    assert declared["protected_scope"]["files"]
    assert stamp["build_base_commit_oid"] == declared["commit"]
    assert stamp["build_tree_oid"] == declared["tree"]
    assert verify_source_bundle._reconstruct_tree(
        declared["files"] + declared["excluded"]
    ) == declared["tree"]
    assert all(
        set(item) == {"path", "reason", "mode", "object_type", "blob"}
        for item in declared["excluded"]
    )

    # FS-SEC-007 / ATK-ZIP-001: verification and extraction remain bound to
    # the original open file description even when the pathname is replaced.
    original_path = tmp_path / "source.original.zip"
    swap_destination = tmp_path / "swap-ignored"
    loaded_manifest, manifest_bytes, files = verify_source_bundle._load_manifest(manifest)
    with verify_source_bundle.open_verified_archive(output) as handle:
        index, expected = verify_source_bundle._verify_open_archive(
            handle, loaded_manifest, manifest_bytes, files,
        )
        output.rename(original_path)
        try:
            with zipfile.ZipFile(output, "w") as attacker:
                attacker.writestr("source/attacker.txt", b"unverified")
            receipt = verify_source_bundle._safe_extract(
                handle,
                index,
                expected,
                swap_destination,
                manifest_digest=hashlib.sha256(manifest_bytes).hexdigest(),
            )
        finally:
            output.unlink(missing_ok=True)
            original_path.rename(output)
    assert receipt["schema_version"] == "butler.firstscreen.archive-extract-receipt.v2"
    assert receipt["terminal_result"] == "VERIFIED_AND_PUBLISHED"
    assert not (swap_destination / "source/attacker.txt").exists()

    with zipfile.ZipFile(output) as archive:
        candidate = next(
            info for info in archive.infolist()
            if info.filename.startswith("source/")
            and info.filename != "source/BUILD_INFO.json"
            and info.file_size > 0
        )
        original = archive.read(candidate)
    forged_archive = tmp_path / "payload-forged.zip"
    replacement = bytes([original[0] ^ 0x01]) + original[1:]
    _rewrite_entry(output, forged_archive, candidate.filename, replacement)
    forged = _verify(root, archive=forged_archive, manifest=manifest, source_root=unpacked / "source")
    assert forged.returncode != 0
    assert forged.stdout.strip() == "SOURCE_BUNDLE_VERIFY_OK=0 ERROR_CODE=SOURCE_BUNDLE_INVALID"

    internal_manifest_forged = tmp_path / "manifest-forged.zip"
    _rewrite_entry(output, internal_manifest_forged, "SOURCE_ARCHIVE_MANIFEST.json", b"{}\n")
    assert _verify(
        root,
        archive=internal_manifest_forged,
        manifest=manifest,
        source_root=unpacked / "source",
    ).returncode != 0

    duplicate = copy.deepcopy(declared)
    duplicate["files"].append(copy.deepcopy(duplicate["files"][0]))
    duplicate["tracked_regular_file_count"] = len(duplicate["files"])
    duplicate_manifest = tmp_path / "duplicate-manifest.json"
    duplicate_manifest.write_text(json.dumps(duplicate, sort_keys=True) + "\n", encoding="utf-8")
    assert _verify(
        root,
        archive=output,
        manifest=duplicate_manifest,
        source_root=unpacked / "source",
    ).returncode != 0

    protected_attack = copy.deepcopy(declared)
    protected_attack["protected_scope"]["protected_paths"] = ["accounting_review"]
    protected_manifest = tmp_path / "protected-scope-forged.json"
    protected_manifest.write_text(json.dumps(protected_attack, sort_keys=True) + "\n", encoding="utf-8")
    assert _verify(
        root,
        archive=output,
        manifest=protected_manifest,
        source_root=unpacked / "source",
    ).returncode != 0

    executable = next((item for item in declared["files"] if item["mode"] == "100755"), None)
    selected = executable or declared["files"][0]
    extracted_path = unpacked / "source" / selected["path"]
    os.chmod(extracted_path, 0o644 if selected["mode"] == "100755" else 0o600)
    mode_attack = _verify(root, archive=output, manifest=manifest, source_root=unpacked / "source")
    assert mode_attack.returncode != 0
    assert not stat.S_IMODE(extracted_path.stat().st_mode) == (0o755 if selected["mode"] == "100755" else 0o644)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-bound extractor uses POSIX dirfd APIs")
def test_descriptor_bound_write_cannot_escape_after_parent_symlink_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "destination"
    outside = tmp_path / "outside"
    destination.mkdir()
    outside.mkdir()
    (destination / "source").mkdir()
    root_fd = os.open(
        destination,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
    )
    original = verify_source_bundle._open_or_create_directory
    swapped = False

    def attack(parent_fd: int, component: str, flags: int) -> int:
        nonlocal swapped
        descriptor = original(parent_fd, component, flags)
        if component == "source" and not swapped:
            os.rename(destination / "source", destination / "detached-source")
            os.symlink(outside, destination / "source", target_is_directory=True)
            swapped = True
        return descriptor

    monkeypatch.setattr(verify_source_bundle, "_open_or_create_directory", attack)
    try:
        verify_source_bundle._write_entry_at(
            root_fd,
            verify_source_bundle._safe_relative_path("source/nested/payload.txt"),
            b"bound-to-open-directory",
            0o644,
        )
    finally:
        os.close(root_fd)

    assert not (outside / "nested/payload.txt").exists()
    assert (destination / "detached-source/nested/payload.txt").read_bytes() == b"bound-to-open-directory"
