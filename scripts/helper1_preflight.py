#!/usr/bin/env python3
"""Reproduce the sealed Helper1 v4 baseline without trusting a branch name."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "contracts" / "helper1" / "baseline-policy-v1.json"
DIGEST = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class PreflightError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _git(repository: Path, arguments: list[str], *, index: Path | None = None) -> bytes:
    environment = os.environ.copy()
    if index is not None:
        environment["GIT_INDEX_FILE"] = str(index)
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=60,
            env=environment,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise PreflightError("BLOCK_BASELINE_UNRESOLVABLE") from error


def _object(value: Any, code: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise PreflightError(code)
    return value


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        return _object(json.loads(path.read_text(encoding="utf-8")), code)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise PreflightError(code) from error


def _policy() -> dict[str, Any]:
    value = _load_json(POLICY_PATH, "BLOCK_BASELINE_UNRESOLVABLE")
    if set(value) != {
        "schema_version",
        "repository_full_name",
        "repository_id",
        "base_commit",
        "base_tree",
        "overlay_manifest_sha256",
        "reconstructed_tree",
    }:
        raise PreflightError("BLOCK_BASELINE_UNRESOLVABLE")
    if (
        value.get("schema_version") != "butler.helper1.baseline-policy.v1"
        or REPOSITORY.fullmatch(str(value.get("repository_full_name"))) is None
        or type(value.get("repository_id")) is not int
        or value["repository_id"] < 1
        or COMMIT.fullmatch(str(value.get("base_commit"))) is None
        or COMMIT.fullmatch(str(value.get("base_tree"))) is None
        or DIGEST.fullmatch(str(value.get("overlay_manifest_sha256"))) is None
        or COMMIT.fullmatch(str(value.get("reconstructed_tree"))) is None
    ):
        raise PreflightError("BLOCK_BASELINE_UNRESOLVABLE")
    return value


def _manifest(path: Path, expected_digest: str) -> dict[str, dict[str, Any]]:
    if _sha256(path) != expected_digest:
        raise PreflightError("BLOCK_OVERLAY_DIGEST_MISMATCH")
    value = _load_json(path, "BLOCK_OVERLAY_DIGEST_MISMATCH")
    if value.get("file_count") != len(value.get("files", [])):
        raise PreflightError("BLOCK_OVERLAY_DIGEST_MISMATCH")
    records: dict[str, dict[str, Any]] = {}
    for record in value.get("files", []):
        if type(record) is not dict or set(record) != {
            "bytes", "kind", "mode", "path", "sha256"
        }:
            raise PreflightError("BLOCK_OVERLAY_DIGEST_MISMATCH")
        relative = record.get("path")
        pure = PurePosixPath(relative) if isinstance(relative, str) else None
        if (
            pure is None
            or pure.is_absolute()
            or ".." in pure.parts
            or relative in records
            or record.get("kind") != "file"
            or type(record.get("bytes")) is not int
            or record["bytes"] < 0
            or record.get("mode") not in {"0o644", "0o755"}
            or DIGEST.fullmatch(str(record.get("sha256"))) is None
        ):
            raise PreflightError("BLOCK_OVERLAY_DIGEST_MISMATCH")
        records[relative] = record
    return records


def _status_paths(repository: Path) -> set[str]:
    raw = _git(repository, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    entries = raw.split(b"\0")
    paths: set[str] = set()
    index = 0
    while index < len(entries) and entries[index]:
        entry = entries[index]
        if len(entry) < 4:
            raise PreflightError("BLOCK_WORKTREE_DIRTY")
        status_code = entry[:2]
        path = entry[3:].decode("utf-8", "strict")
        if status_code[:1] in {b"R", b"C"}:
            index += 1
            if index >= len(entries) or not entries[index]:
                raise PreflightError("BLOCK_WORKTREE_DIRTY")
            path = entries[index].decode("utf-8", "strict")
        paths.add(path)
        index += 1
    return paths


def _verify_overlay(repository: Path, records: dict[str, dict[str, Any]]) -> None:
    if _status_paths(repository) != set(records):
        raise PreflightError("BLOCK_WORKTREE_DIRTY")
    for relative, record in records.items():
        path = repository / relative
        try:
            info = path.lstat()
        except OSError as error:
            raise PreflightError("BLOCK_OVERLAY_DIGEST_MISMATCH") from error
        expected_mode = int(record["mode"], 8)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != expected_mode
            or info.st_size != record["bytes"]
            or _sha256(path) != record["sha256"]
        ):
            raise PreflightError("BLOCK_OVERLAY_DIGEST_MISMATCH")


def build_deterministic_overlay_tar(
    repository: Path,
    records: dict[str, dict[str, Any]],
    destination: Path,
) -> None:
    """Write only manifest files with deterministic, xattr-free metadata."""
    _verify_overlay(repository, records)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".helper1-overlay-", suffix=".tar.gz", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as raw_stream:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_stream, mtime=0
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed,
                    mode="w",
                    format=tarfile.USTAR_FORMAT,
                ) as archive:
                    for relative in sorted(records):
                        record = records[relative]
                        payload = (repository / relative).read_bytes()
                        info = tarfile.TarInfo(relative)
                        info.size = len(payload)
                        info.mode = int(record["mode"], 8)
                        info.mtime = 0
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        info.pax_headers = {}
                        archive.addfile(info, io.BytesIO(payload))
            raw_stream.flush()
            os.fsync(raw_stream.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def verify_deterministic_overlay_tar(
    archive_path: Path,
    records: dict[str, dict[str, Any]],
) -> None:
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if names != sorted(records) or len(names) != len(set(names)):
                raise PreflightError("BLOCK_OVERLAY_TAR_INVALID")
            for member in members:
                pure = PurePosixPath(member.name)
                if (
                    pure.name.startswith("._")
                    or "__MACOSX" in pure.parts
                    or not member.isfile()
                    or member.issym()
                    or member.islnk()
                    or member.uid != 0
                    or member.gid != 0
                    or member.mtime != 0
                    or member.uname not in {"", None}
                    or member.gname not in {"", None}
                    or member.pax_headers
                    or member.mode != int(records[member.name]["mode"], 8)
                ):
                    raise PreflightError("BLOCK_OVERLAY_TAR_INVALID")
                stream = archive.extractfile(member)
                if stream is None:
                    raise PreflightError("BLOCK_OVERLAY_TAR_INVALID")
                payload = stream.read()
                if (
                    len(payload) != records[member.name]["bytes"]
                    or hashlib.sha256(payload).hexdigest()
                    != records[member.name]["sha256"]
                ):
                    raise PreflightError("BLOCK_OVERLAY_TAR_INVALID")
    except (KeyError, OSError, tarfile.TarError) as error:
        raise PreflightError("BLOCK_OVERLAY_TAR_INVALID") from error


def _reconstructed_tree(repository: Path, base_commit: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory(prefix="helper1-preflight-index-") as directory:
        index = Path(directory) / "index"
        _git(repository, ["read-tree", base_commit], index=index)
        _git(repository, ["add", "-A"], index=index)
        tree = _git(repository, ["write-tree"], index=index).decode("ascii").strip()
        inventory = _git(repository, ["ls-files", "-s", "-z"], index=index)
    return tree, hashlib.sha256(inventory).hexdigest()


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".helper1-preflight-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def verify(arguments: argparse.Namespace) -> dict[str, Any]:
    policy = _policy()
    repository = arguments.repository.resolve(strict=True)
    if (
        arguments.repository_full_name != policy["repository_full_name"]
        or arguments.repository_id != policy["repository_id"]
        or arguments.base_commit != policy["base_commit"]
        or arguments.base_tree != policy["base_tree"]
        or arguments.overlay_sha256 != policy["overlay_manifest_sha256"]
        or arguments.reconstructed_tree != policy["reconstructed_tree"]
    ):
        raise PreflightError("BLOCK_BASELINE_UNRESOLVABLE")
    _git(repository, ["cat-file", "-e", f"{arguments.base_commit}^{{commit}}"])
    _git(repository, ["cat-file", "-e", f"{arguments.base_tree}^{{tree}}"])
    observed_tree = _git(
        repository, ["show", "-s", "--format=%T", arguments.base_commit]
    ).decode("ascii").strip()
    if observed_tree != arguments.base_tree:
        raise PreflightError("BLOCK_BASE_TREE_MISMATCH")
    records = _manifest(arguments.overlay_manifest, arguments.overlay_sha256)
    _verify_overlay(repository, records)
    tree, source_digest = _reconstructed_tree(repository, arguments.base_commit)
    if tree != arguments.reconstructed_tree:
        raise PreflightError("BLOCK_OVERLAY_DIGEST_MISMATCH")
    return {
        "schema_version": "butler.helper1.preflight-receipt.v1",
        "repository_full_name": arguments.repository_full_name,
        "repository_id": arguments.repository_id,
        "base_commit": arguments.base_commit,
        "base_tree": arguments.base_tree,
        "overlay_manifest_sha256": arguments.overlay_sha256,
        "overlay_file_count": len(records),
        "reconstructed_tree": tree,
        "source_inventory_sha256": source_digest,
        "preflight_ok": True,
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--repository-full-name", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--base-tree", required=True)
    parser.add_argument("--overlay-manifest", required=True, type=Path)
    parser.add_argument("--overlay-sha256", required=True)
    parser.add_argument("--reconstructed-tree", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    try:
        receipt = verify(arguments)
        _write_receipt(arguments.receipt, receipt)
    except (OSError, UnicodeError, PreflightError) as error:
        code = str(error)
        if code not in {
            "BLOCK_BASELINE_UNRESOLVABLE",
            "BLOCK_BASE_TREE_MISMATCH",
            "BLOCK_OVERLAY_DIGEST_MISMATCH",
            "BLOCK_WORKTREE_DIRTY",
        }:
            code = "BLOCK_BASELINE_UNRESOLVABLE"
        print("PREFLIGHT_OK=0")
        print(f"ERROR_CODE={code}")
        return 1
    print("PREFLIGHT_OK=1")
    print("ERROR_CODE=NONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
