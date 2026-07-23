#!/usr/bin/env python3
"""Build a deterministic, regular-file-only source archive from a Git tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import zipfile
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# TEMPORARY: main's v5.7 rework privatized the seven-field stamp builder as
# scripts.write_build_info._validated_payload (dropping the public
# validated_build_info_payload). We call the private helper here so this
# FirstScreen safe-source archive keeps its exact stamp contract without
# re-adding a firstscreen-specific API to main's file. Cleanup item: add a
# public wrapper to main and switch this import back (tracked in PR #868).
from scripts.write_build_info import _validated_payload
from scripts.release.firstscreen_source_contracts import (
    PORTABLE_PATH_POLICY,
    PROTECTED_CONTRACT_ID,
    PROTECTED_PATHS,
    SourceContractError,
    is_protected_path,
    portable_path_key,
    protected_contract_digest,
    protected_pathspecs,
)


BANNED_COMPONENTS = {".DS_Store", ".cursor", "node_modules", "dist", "target", "__pycache__"}


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def git_blobs(object_ids: list[str]) -> dict[str, bytes]:
    """Read all Git blobs through one batch process, preserving object identity."""

    completed = subprocess.run(
        ["git", "cat-file", "--batch"],
        input="".join(f"{oid}\n" for oid in object_ids).encode("ascii"),
        check=True,
        capture_output=True,
        timeout=300,
    )
    stream = BytesIO(completed.stdout)
    result: dict[str, bytes] = {}
    for requested in object_ids:
        header = stream.readline().decode("ascii", errors="strict").rstrip("\n")
        parts = header.split()
        if len(parts) != 3 or parts[1] != "blob" or not parts[2].isdigit():
            raise RuntimeError("git cat-file batch returned an invalid object")
        size = int(parts[2])
        payload = stream.read(size)
        if len(payload) != size or stream.read(1) != b"\n":
            raise RuntimeError("git cat-file batch returned a truncated object")
        result[requested] = payload
    if stream.read(1):
        raise RuntimeError("git cat-file batch returned trailing data")
    return result


def safe_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or any(part in BANNED_COMPONENTS for part in path.parts):
        raise ValueError(f"unsafe path: {raw}")
    return path


def zip_info(path: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    permissions = 0o755 if executable else 0o644
    info.external_attr = (stat.S_IFREG | permissions) << 16
    return info


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--scope-baseline", required=True)
    arguments = parser.parse_args()

    commit = git("rev-parse", arguments.commit).decode().strip()
    tree = git("rev-parse", f"{commit}^{{tree}}").decode().strip()
    baseline = git("rev-parse", f"{arguments.scope_baseline}^{{commit}}").decode().strip()
    protected_specs = protected_pathspecs()
    protected_changes = [
        path
        for path in git(
            "diff", "--name-only", baseline, commit, "--", *protected_specs
        ).decode("utf-8").splitlines()
        if path
    ]
    if protected_changes:
        raise ValueError("protected first-screen scope changed")
    commit_timestamp = int(git("show", "-s", "--format=%ct", commit).decode().strip())
    timestamp_utc = datetime.fromtimestamp(commit_timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    describe = git("describe", "--always", commit).decode().strip()
    package = json.loads(Path("butler-desktop/package.json").read_text(encoding="utf-8"))
    build_stamp = _validated_payload(
        build_oid=commit,
        build_tree_oid=tree,
        git_describe=describe,
        timestamp_utc=timestamp_utc,
        app_version=str(package["version"]),
    )
    # _validated_payload hardcodes builder="build_complete_app.sh"; restore the
    # archive's own builder label so the stamp bytes are unchanged from before.
    build_stamp["builder"] = "build_safe_source_archive.py"
    build_stamp_bytes = (json.dumps(build_stamp, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    entries = git("ls-tree", "-r", "-z", commit).split(b"\0")
    parsed_entries: list[tuple[str, str, str, str]] = []
    for entry in entries:
        if entry:
            metadata, raw_path = entry.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split()
            parsed_entries.append((mode, object_type, object_id, raw_path.decode("utf-8")))
    blobs = git_blobs(
        [object_id for mode, object_type, object_id, _path in parsed_entries if mode in {"100644", "100755"} and object_type == "blob"]
    )
    files: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    payloads: list[tuple[str, bytes, bool]] = []
    portable_paths: dict[str, str] = {}

    for mode, object_type, object_id, path_text in parsed_entries:
        path = PurePosixPath(path_text)
        if mode == "120000":
            excluded.append({
                "path": path_text,
                "reason": "SYMLINK_EXCLUDED",
                "mode": mode,
                "object_type": object_type,
                "blob": object_id,
            })
            continue
        if mode not in {"100644", "100755"} or object_type != "blob":
            excluded.append({
                "path": path_text,
                "reason": "NON_REGULAR_EXCLUDED",
                "mode": mode,
                "object_type": object_type,
                "blob": object_id,
            })
            continue
        if path.is_absolute() or ".." in path.parts or any(part in BANNED_COMPONENTS for part in path.parts):
            excluded.append({
                "path": path_text,
                "reason": "BANNED_PATH_EXCLUDED",
                "mode": mode,
                "object_type": object_type,
                "blob": object_id,
            })
            continue
        safe_path(path_text)
        try:
            portable_key = portable_path_key(path_text)
        except SourceContractError as exc:
            raise ValueError(f"non-portable source path: {path_text!r}") from exc
        if portable_key in portable_paths:
            raise ValueError(
                f"portable path collision: {portable_paths[portable_key]!r} and {path_text!r}"
            )
        portable_paths[portable_key] = path_text
        content = blobs[object_id]
        digest = hashlib.sha256(content).hexdigest()
        files.append({"path": path_text, "mode": mode, "blob": object_id, "sha256": digest, "size": len(content)})
        payloads.append((f"source/{path_text}", content, mode == "100755"))

    protected_files = [dict(item) for item in files if is_protected_path(str(item["path"]))]
    manifest = {
        "schema_version": "butler.safe-source-manifest.v2",
        "portable_path_policy": PORTABLE_PATH_POLICY,
        "protected_scope": {
            "schema_version": "butler.firstscreen.protected-scope.v2",
            "contract_id": PROTECTED_CONTRACT_ID,
            "contract_digest": protected_contract_digest(),
            "baseline_commit": baseline,
            "target_commit": commit,
            "protected_paths": list(PROTECTED_PATHS),
            "changed_paths": [],
            "verified_unchanged": True,
            "files": protected_files,
        },
        "commit": commit,
        "tree": tree,
        "policy": "REGULAR_TRACKED_FILES_ONLY",
        "tracked_tree_entry_count": len([entry for entry in entries if entry]),
        "tracked_regular_file_count": len(files),
        "archive_source_entry_count": len(payloads),
        "archive_generated_entry_count": 2,
        "archive_manifest_entry_count": 1,
        "archive_entry_count": len(payloads) + 2,
        "self_manifest": {
            "path": "SOURCE_ARCHIVE_MANIFEST.json",
            "self_excluded_from_tracked_set": True,
            "reason": "GENERATED_ARCHIVE_METADATA",
        },
        "build_stamp": {
            "path": "source/BUILD_INFO.json",
            "sha256": hashlib.sha256(build_stamp_bytes).hexdigest(),
            "size": len(build_stamp_bytes),
            "commit": commit,
            "tree": tree,
            "generated_from_git_object": True,
        },
        "excluded_count": len(excluded),
        "files": files,
        "excluded": excluded,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_bytes(manifest_bytes)
    os.chmod(arguments.manifest, 0o644)
    with zipfile.ZipFile(arguments.output, "w", strict_timestamps=True) as archive:
        for path, content, executable in sorted(payloads):
            archive.writestr(zip_info(path, executable), content)
        archive.writestr(zip_info("source/BUILD_INFO.json"), build_stamp_bytes)
        archive.writestr(zip_info("SOURCE_ARCHIVE_MANIFEST.json"), manifest_bytes)

    with zipfile.ZipFile(arguments.output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("archive CRC verification failed")
        infos = archive.infolist()
        expected_names = {path for path, _content, _executable in payloads} | {
            "source/BUILD_INFO.json", "SOURCE_ARCHIVE_MANIFEST.json",
        }
        actual_names = {info.filename for info in infos}
        if len(infos) != len(actual_names) or actual_names != expected_names:
            raise RuntimeError("archive set does not exactly match tracked regular files plus self manifest")
        expected_files = {f"source/{item['path']}": item for item in files}
        for info in infos:
            file_type = (info.external_attr >> 16) & 0o170000
            if file_type != stat.S_IFREG:
                raise RuntimeError(f"non-regular archive entry: {info.filename}")
            safe_path(info.filename)
            payload = archive.read(info.filename)
            if info.filename == "SOURCE_ARCHIVE_MANIFEST.json":
                if payload != manifest_bytes:
                    raise RuntimeError("self manifest bytes mismatch")
                continue
            if info.filename == "source/BUILD_INFO.json":
                if payload != build_stamp_bytes:
                    raise RuntimeError("build stamp bytes mismatch")
                continue
            expected = expected_files[info.filename]
            if hashlib.sha256(payload).hexdigest() != expected["sha256"] or len(payload) != expected["size"]:
                raise RuntimeError(f"archive content mismatch: {info.filename}")
            archive_mode = (info.external_attr >> 16) & 0o777
            expected_mode = 0o755 if expected["mode"] == "100755" else 0o644
            if archive_mode != expected_mode:
                raise RuntimeError(f"archive mode mismatch: {info.filename}")
    print(json.dumps({"status": "PASS", "commit": commit, "tree": tree, "tracked_regular_files": len(files), "archive_entries": len(payloads) + 2, "build_stamp_included": True, "self_manifest_excluded": True, "excluded": len(excluded), "archive_sha256": hashlib.sha256(arguments.output.read_bytes()).hexdigest()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
