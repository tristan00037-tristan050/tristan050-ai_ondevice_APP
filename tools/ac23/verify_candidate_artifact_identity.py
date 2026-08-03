#!/usr/bin/env python3
"""Independent, network-free verifier for Butler AC-23 artifacts.

The script is intentionally self-contained so the exact file can be copied to
``AC23_FINAL/VERIFY`` and executed without importing candidate source code.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
import urllib.parse
import zlib
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "butler.box5.candidate-artifact-identity.v1"
APPROVED_REPOSITORY_URL = (
    "https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP.git"
)
APPROVED_BASE_COMMIT = "de3dd4ebaf5b3935a142b988dd61e6198aa9536d"
APPROVED_BASE_TREE = "8c3509db047145714d2a1a84dfc76fb0a4c0fec9"
NORMATIVE_CONTRACT_PATH = (
    "butler_pc_core/accounting/assignment/contracts/authorization-replay-v2.sql"
)
NORMATIVE_CONTRACT_SHA256 = (
    "b0e11b52b7efd3d74c41fcfb46726312ba442c2dfa7a7a04203f7424342bd729"
)
MAX_MEMBERS = 100_000
MAX_MEMBER_SIZE = 1 << 30
MAX_TOTAL_SIZE = 4 << 30
MAX_MANIFEST_SIZE = 1 << 20
MANIFEST_KEYS = {
    "schema_version",
    "digest_algorithm",
    "repository_url",
    "object_format",
    "base_commit",
    "base_tree",
    "head_commit",
    "head_tree",
    "submitted_head_tree",
    "patch_applied_tree",
    "source_archive_tree",
    "patch_sha256",
    "source_archive_sha256",
    "changed_path_manifest_sha256",
    "evidence_sha256",
    "normative_contract_path",
    "normative_contract_sha256",
}
PACKAGE_FILES = {
    "IDENTITY/candidate_artifact_identity.json",
    "IDENTITY/changed_paths.nul",
    "PATCH/cumulative.patch",
    "SOURCE/candidate_source.tar",
    "SOURCE/candidate_repository.bundle",
    "EVIDENCE/evidence_raw.tar",
    "VERIFY/verify_candidate_artifact_identity.py",
    "VERIFY/candidate-artifact-identity-v1.schema.json",
    "README_KO.md",
    "SHA256SUMS.txt",
}


class VerificationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fail(code: str) -> None:
    raise VerificationError(code)


def _git_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    for key in ("PATH", "SYSTEMROOT", "TMPDIR"):
        if key in os.environ:
            env[key] = os.environ[key]
    env.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    if extra:
        env.update(extra)
    return env


def _git(
    cwd: Path,
    *args: str | os.PathLike[str],
    input_bytes: bytes | None = None,
    check: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    argv = [
        "git",
        "-c",
        "core.autocrlf=false",
        "-c",
        "core.safecrlf=false",
        "-c",
        "core.filemode=true",
        "-c",
        "core.symlinks=true",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        f"core.excludesFile={os.devnull}",
        *(os.fspath(arg) for arg in args),
    ]
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=_git_env(extra_env),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, argv, output=result.stdout, stderr=result.stderr
        )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _same(left: str | bytes, right: str | bytes) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return hmac.compare_digest(left.encode("ascii"), right.encode("ascii"))
    if isinstance(left, bytes) and isinstance(right, bytes):
        return hmac.compare_digest(left, right)
    return False


def normalize_repository_url(raw: str) -> str:
    if not isinstance(raw, str):
        fail("E_REPOSITORY_URL")
    value = raw.strip().rstrip("/")
    scp = re.fullmatch(r"git@([^:/\s]+):(.+)", value)
    if scp:
        value = f"ssh://git@{scp.group(1)}/{scp.group(2)}"
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        fail("E_REPOSITORY_URL")
    scheme = parsed.scheme.lower()
    if scheme not in {"https", "ssh"} or not parsed.hostname:
        fail("E_REPOSITORY_URL")
    if parsed.query or parsed.fragment or parsed.password is not None:
        fail("E_REPOSITORY_URL")
    username = parsed.username
    if username is not None and not (scheme == "ssh" and username == "git"):
        fail("E_REPOSITORY_URL")
    if "\\" in parsed.path or not parsed.path.startswith("/"):
        fail("E_REPOSITORY_URL")
    path = parsed.path.rstrip("/")
    parts = path.split("/")[1:]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        fail("E_REPOSITORY_URL")
    host = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError:
        fail("E_REPOSITORY_URL")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = ("git@" if username else "") + host
    if port is not None:
        netloc += f":{port}"
    return urllib.parse.urlunsplit((scheme, netloc, path, "", ""))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            fail("E_SCHEMA")
        output[key] = value
    return output


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError:
        fail("E_SCHEMA")
    if len(raw) > MAX_MANIFEST_SIZE:
        fail("E_SCHEMA")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, VerificationError):
        fail("E_SCHEMA")
    if not isinstance(value, dict) or set(value) != MANIFEST_KEYS:
        fail("E_SCHEMA")
    if value.get("schema_version") != SCHEMA_VERSION:
        fail("E_SCHEMA")
    if value.get("digest_algorithm") != "sha256":
        fail("E_SCHEMA")
    if value.get("object_format") not in {"sha1", "sha256"}:
        fail("E_SCHEMA")
    oid_length = 40 if value["object_format"] == "sha1" else 64
    for key in (
        "base_commit",
        "base_tree",
        "head_commit",
        "head_tree",
        "submitted_head_tree",
        "patch_applied_tree",
        "source_archive_tree",
    ):
        field = value.get(key)
        if not isinstance(field, str) or not re.fullmatch(
            rf"[0-9a-f]{{{oid_length}}}", field
        ):
            fail("E_SCHEMA")
    for key in (
        "patch_sha256",
        "source_archive_sha256",
        "changed_path_manifest_sha256",
        "evidence_sha256",
        "normative_contract_sha256",
    ):
        field = value.get(key)
        if not isinstance(field, str) or not re.fullmatch(r"[0-9a-f]{64}", field):
            fail("E_SCHEMA")
    if not isinstance(value.get("repository_url"), str):
        fail("E_SCHEMA")
    if not isinstance(value.get("normative_contract_path"), str):
        fail("E_SCHEMA")
    return value


def _archive_segments(name: str) -> tuple[str, ...]:
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        fail("E_ARCHIVE_SAFETY")
    parts = tuple(name.rstrip("/").split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        fail("E_ARCHIVE_SAFETY")
    if any(part.casefold() == ".git" for part in parts):
        fail("E_ARCHIVE_SAFETY")
    return parts


def _inspect_source_tar(path: Path) -> list[tarfile.TarInfo]:
    try:
        archive = tarfile.open(path, "r:*", encoding="utf-8", errors="surrogateescape")
    except (OSError, tarfile.TarError):
        fail("E_ARCHIVE_SAFETY")
    members: list[tarfile.TarInfo] = []
    exact: set[str] = set()
    folded: dict[str, str] = {}
    symlinks: set[str] = set()
    total = 0
    try:
        with archive:
            for index, member in enumerate(archive):
                if index >= MAX_MEMBERS:
                    fail("E_ARCHIVE_SAFETY")
                parts = _archive_segments(member.name)
                if parts[0] != "candidate":
                    fail("E_ARCHIVE_SAFETY")
                canonical = "/".join(parts)
                if canonical in exact:
                    fail("E_ARCHIVE_SAFETY")
                exact.add(canonical)
                folded_key = "/".join(
                    unicodedata.normalize("NFC", part).casefold() for part in parts
                )
                if folded_key in folded and folded[folded_key] != canonical:
                    fail("E_ARCHIVE_SAFETY")
                folded[folded_key] = canonical
                if any(
                    "/".join(parts[:depth]) in symlinks
                    for depth in range(1, len(parts))
                ):
                    fail("E_ARCHIVE_SAFETY")
                if member.islnk() or member.ischr() or member.isblk() or member.isfifo():
                    fail("E_ARCHIVE_SAFETY")
                if not (member.isdir() or member.isfile() or member.issym()):
                    fail("E_ARCHIVE_SAFETY")
                if member.size < 0 or member.size > MAX_MEMBER_SIZE:
                    fail("E_ARCHIVE_SAFETY")
                total += member.size
                if total > MAX_TOTAL_SIZE:
                    fail("E_ARCHIVE_SAFETY")
                if member.issym():
                    target = member.linkname
                    if (
                        not target
                        or target.startswith("/")
                        or "\\" in target
                        or "\x00" in target
                        or "" in target.split("/")
                    ):
                        fail("E_ARCHIVE_SAFETY")
                    resolved = posixpath.normpath(
                        posixpath.join(*parts[:-1], target)
                    )
                    if resolved == "candidate" or not resolved.startswith("candidate/"):
                        fail("E_ARCHIVE_SAFETY")
                    symlinks.add(canonical)
                members.append(member)
    except (OSError, tarfile.TarError):
        fail("E_ARCHIVE_SAFETY")
    return members


def _validate_evidence_tar(path: Path, manifest: dict[str, Any]) -> None:
    required = {
        "environment.txt",
        "commands.jsonl",
        "clean_status.bin",
        "tree_reconstruction.json",
        "regression/frozen_19_summary.json",
        "mutation/mutation_20_summary.json",
    }
    seen: set[str] = set()
    folded: dict[str, str] = {}
    payloads: dict[str, bytes] = {}
    total = 0
    try:
        archive = tarfile.open(path, "r:", encoding="utf-8", errors="strict")
        with archive:
            for index, member in enumerate(archive):
                if index >= MAX_MEMBERS:
                    fail("E_EVIDENCE_DIGEST")
                parts = _archive_segments(member.name)
                canonical = "/".join(parts)
                if canonical in seen:
                    fail("E_EVIDENCE_DIGEST")
                seen.add(canonical)
                folded_key = "/".join(
                    unicodedata.normalize("NFC", part).casefold() for part in parts
                )
                if folded_key in folded and folded[folded_key] != canonical:
                    fail("E_EVIDENCE_DIGEST")
                folded[folded_key] = canonical
                if not (member.isdir() or member.isfile()):
                    fail("E_EVIDENCE_DIGEST")
                if member.size < 0 or member.size > MAX_MEMBER_SIZE:
                    fail("E_EVIDENCE_DIGEST")
                total += member.size
                if total > MAX_TOTAL_SIZE:
                    fail("E_EVIDENCE_DIGEST")
                if member.isfile():
                    source = archive.extractfile(member)
                    if source is None:
                        fail("E_EVIDENCE_DIGEST")
                    payloads[canonical] = source.read()
    except VerificationError:
        raise
    except (OSError, UnicodeError, tarfile.TarError):
        fail("E_EVIDENCE_DIGEST")
    if not required.issubset(payloads):
        fail("E_EVIDENCE_DIGEST")
    forbidden_path_markers = (b"/Users/", b"/private/tmp/", b"\\Users\\")
    if any(
        marker in payload
        for payload in payloads.values()
        for marker in forbidden_path_markers
    ):
        fail("E_EVIDENCE_DIGEST")
    if payloads["clean_status.bin"] != b"":
        fail("E_CLEAN_STATUS")
    try:
        environment = payloads["environment.txt"].decode("utf-8")
        if not all(
            marker in environment
            for marker in ("os=", "architecture=", "git=", "python=", "locale=C", "timezone=UTC")
        ):
            fail("E_EVIDENCE_DIGEST")
        command_lines = payloads["commands.jsonl"].decode("utf-8").splitlines()
        if not command_lines:
            fail("E_EVIDENCE_DIGEST")
        for expected_sequence, line in enumerate(command_lines, start=1):
            entry = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
            if not isinstance(entry, dict) or set(entry) != {
                "sequence",
                "argv",
                "cwd",
                "start_utc",
                "end_utc",
                "exit_code",
            }:
                fail("E_EVIDENCE_DIGEST")
            if entry["sequence"] != expected_sequence:
                fail("E_EVIDENCE_DIGEST")
            if not isinstance(entry["argv"], list) or not all(
                isinstance(item, str) and item for item in entry["argv"]
            ):
                fail("E_EVIDENCE_DIGEST")
            if (
                not isinstance(entry["cwd"], str)
                or entry["cwd"].startswith("/")
                or ".." in entry["cwd"].split("/")
            ):
                fail("E_EVIDENCE_DIGEST")
            if not isinstance(entry["exit_code"], int):
                fail("E_EVIDENCE_DIGEST")
            for time_key in ("start_utc", "end_utc"):
                if not isinstance(entry[time_key], str) or not entry[time_key].endswith("Z"):
                    fail("E_EVIDENCE_DIGEST")
        reconstruction = json.loads(payloads["tree_reconstruction.json"].decode("utf-8"))
        if reconstruction != {
            "head_tree": manifest["head_tree"],
            "patch_applied_tree": manifest["patch_applied_tree"],
            "source_archive_tree": manifest["source_archive_tree"],
            "submitted_head_tree": manifest["submitted_head_tree"],
        }:
            fail("E_EVIDENCE_DIGEST")
        regression = json.loads(
            payloads["regression/frozen_19_summary.json"].decode("utf-8")
        )
        if regression != {"failed": 0, "passed": 19, "total": 19}:
            fail("E_EVIDENCE_DIGEST")
        mutation = json.loads(
            payloads["mutation/mutation_20_summary.json"].decode("utf-8")
        )
        if mutation != {"failed": 0, "passed": 20, "total": 20}:
            fail("E_EVIDENCE_DIGEST")
    except VerificationError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        fail("E_EVIDENCE_DIGEST")


def _extract_source_tar(path: Path, destination: Path, members: list[tarfile.TarInfo]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = tarfile.open(path, "r:*", encoding="utf-8", errors="surrogateescape")
        with archive:
            materialized = {member.name: member for member in archive.getmembers()}
            for member in members:
                if member.issym():
                    continue
                parts = _archive_segments(member.name)
                output = destination.joinpath(*parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                if member.isdir():
                    output.mkdir(exist_ok=True)
                    os.chmod(output, member.mode & 0o777)
                    continue
                source = archive.extractfile(materialized[member.name])
                if source is None:
                    fail("E_ARCHIVE_SAFETY")
                with source, output.open("xb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                os.chmod(output, member.mode & 0o777)
            for member in members:
                if not member.issym():
                    continue
                parts = _archive_segments(member.name)
                output = destination.joinpath(*parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(member.linkname, output)
    except (OSError, tarfile.TarError):
        fail("E_ARCHIVE_SAFETY")


def _write_loose_blob(repository: Path, payload: bytes, object_format: str) -> bytes:
    framed = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    oid = hashlib.new(object_format, framed).hexdigest().encode("ascii")
    object_path = repository / ".git" / "objects" / oid[:2].decode("ascii") / oid[2:].decode("ascii")
    if not object_path.exists():
        object_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = object_path.with_name(object_path.name + ".tmp")
        with temporary.open("xb") as stream:
            stream.write(zlib.compress(framed))
        os.replace(temporary, object_path)
    return oid


def _source_tree(
    path: Path, temporary: Path, object_format: str = "sha1"
) -> tuple[str, bool]:
    temporary.mkdir(parents=True, exist_ok=True)
    members = _inspect_source_tar(path)
    _extract_source_tar(path, temporary / "extracted", members)
    repository = temporary / "tree-repository"
    repository.mkdir()
    try:
        _git(repository, "init", "--quiet", f"--object-format={object_format}")
    except subprocess.CalledProcessError:
        fail("E_SOURCE_TREE")
    rows: list[tuple[bytes, bytes]] = []
    self_reference = False
    try:
        archive = tarfile.open(path, "r:*", encoding="utf-8", errors="surrogateescape")
        with archive:
            by_name = {member.name: member for member in archive.getmembers()}
            for member in members:
                parts = _archive_segments(member.name)
                if len(parts) == 1 or member.isdir():
                    continue
                relative = "/".join(parts[1:]).encode("utf-8", "surrogateescape")
                if parts[-1] == "candidate_artifact_identity.json":
                    self_reference = True
                if member.issym():
                    payload = member.linkname.encode("utf-8", "surrogateescape")
                    mode = b"120000"
                else:
                    source = archive.extractfile(by_name[member.name])
                    if source is None:
                        fail("E_SOURCE_TREE")
                    payload = source.read()
                    mode = b"100755" if member.mode & 0o111 else b"100644"
                    if member.name.endswith(".json") and len(payload) <= MAX_MANIFEST_SIZE:
                        try:
                            parsed = json.loads(payload.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            parsed = None
                        if isinstance(parsed, dict) and parsed.get("schema_version") == SCHEMA_VERSION:
                            self_reference = True
                oid = _write_loose_blob(repository, payload, object_format)
                rows.append((relative, mode + b" " + oid + b"\t" + relative + b"\0"))
        rows.sort(key=lambda item: item[0])
        index_input = b"".join(row for _, row in rows)
        _git(repository, "update-index", "-z", "--index-info", input_bytes=index_input)
        tree = _git(repository, "write-tree").stdout.decode("ascii").strip()
    except (OSError, tarfile.TarError, subprocess.CalledProcessError):
        fail("E_SOURCE_TREE")
    return tree, self_reference


def _changed_paths(repository: Path, base: str, head: str) -> bytes:
    try:
        output = _git(
            repository,
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            base,
            head,
            "--",
        ).stdout
    except subprocess.CalledProcessError:
        fail("E_CHANGED_PATH_DIGEST")
    if output and not output.endswith(b"\0"):
        fail("E_CHANGED_PATH_DIGEST")
    paths = output[:-1].split(b"\0") if output else []
    if len(paths) != len(set(paths)):
        fail("E_CHANGED_PATH_DIGEST")
    for path in paths:
        if not path or path.startswith(b"/") or b"\\" in path:
            fail("E_CHANGED_PATH_DIGEST")
        if any(segment in {b"", b".", b".."} for segment in path.split(b"/")):
            fail("E_CHANGED_PATH_DIGEST")
    return b"".join(path + b"\0" for path in sorted(paths))


def _prepare_bundle(bundle: Path, temporary: Path, manifest: dict[str, Any]) -> tuple[Path, str]:
    repository = temporary / "bundle-repository"
    repository.mkdir()
    try:
        _git(repository, "init", "--bare", "--quiet")
        verified = _git(repository, "bundle", "verify", bundle)
        verification_text = (verified.stdout + verified.stderr).decode("utf-8", "replace")
        if "complete history" not in verification_text.lower():
            fail("E_BUNDLE")
        heads = _git(repository, "bundle", "list-heads", bundle).stdout.splitlines()
        selected_ref: str | None = None
        for line in heads:
            oid, separator, ref = line.partition(b" ")
            if separator and oid.decode("ascii", "strict") == manifest["head_commit"]:
                selected_ref = ref.decode("utf-8", "surrogateescape")
                break
        if selected_ref is None:
            fail("E_HEAD_OBJECT")
        _git(
            repository,
            "fetch",
            "--no-tags",
            bundle,
            f"{selected_ref}:refs/ac23/candidate",
        )
        object_format = _git(repository, "rev-parse", "--show-object-format").stdout.decode(
            "ascii"
        ).strip()
    except VerificationError:
        raise
    except (UnicodeError, subprocess.CalledProcessError):
        fail("E_BUNDLE")
    return repository, object_format


def _verify_objects(repository: Path, manifest: dict[str, Any], object_format: str) -> None:
    if object_format != manifest["object_format"]:
        fail("E_SCHEMA")
    try:
        if _git(repository, "cat-file", "-t", manifest["base_commit"]).stdout.strip() != b"commit":
            fail("E_BASE_OBJECT")
    except subprocess.CalledProcessError:
        fail("E_BASE_OBJECT")
    try:
        actual_base_tree = _git(
            repository, "show", "-s", "--format=%T", manifest["base_commit"]
        ).stdout.decode("ascii").strip()
    except (UnicodeError, subprocess.CalledProcessError):
        fail("E_BASE_TREE")
    if not _same(actual_base_tree, manifest["base_tree"]):
        fail("E_BASE_TREE")
    try:
        if _git(repository, "cat-file", "-t", manifest["head_commit"]).stdout.strip() != b"commit":
            fail("E_HEAD_OBJECT")
    except subprocess.CalledProcessError:
        fail("E_HEAD_OBJECT")
    try:
        actual_head_tree = _git(
            repository, "show", "-s", "--format=%T", manifest["head_commit"]
        ).stdout.decode("ascii").strip()
    except (UnicodeError, subprocess.CalledProcessError):
        fail("E_HEAD_TREE")
    if not _same(actual_head_tree, manifest["head_tree"]):
        fail("E_HEAD_TREE")
    ancestry = _git(
        repository,
        "merge-base",
        "--is-ancestor",
        manifest["base_commit"],
        manifest["head_commit"],
        check=False,
    )
    if ancestry.returncode != 0:
        fail("E_ANCESTRY")


def _patch_tree(bundle: Path, patch: Path, temporary: Path, manifest: dict[str, Any]) -> str:
    repository = temporary / "patch-repository"
    repository.mkdir()
    try:
        _git(repository, "init", "--quiet")
        _git(
            repository,
            "fetch",
            "--no-tags",
            bundle,
            "refs/heads/candidate:refs/ac23/candidate",
        )
        _git(repository, "checkout", "--detach", "--force", manifest["base_commit"])
        before = _git(
            repository, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        ).stdout
        if before:
            fail("E_CLEAN_STATUS")
        checked = _git(repository, "apply", "--check", "--binary", patch, check=False)
        if checked.returncode != 0:
            fail("E_PATCH_APPLY")
        applied = _git(
            repository, "apply", "--binary", "--index", patch, check=False
        )
        if applied.returncode != 0:
            fail("E_PATCH_APPLY")
        if _git(repository, "diff", "--cached", "--check", check=False).returncode != 0:
            fail("E_PATCH_APPLY")
        status = _git(
            repository, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        ).stdout
        if any(record.startswith(b"?? ") for record in status.split(b"\0") if record):
            fail("E_PATCH_APPLY")
        return _git(repository, "write-tree").stdout.decode("ascii").strip()
    except VerificationError:
        raise
    except (UnicodeError, subprocess.CalledProcessError):
        fail("E_PATCH_APPLY")


def _checkout_clean(bundle: Path, temporary: Path, manifest: dict[str, Any]) -> None:
    repository = temporary / "checkout-repository"
    repository.mkdir()
    try:
        _git(repository, "init", "--quiet")
        _git(
            repository,
            "fetch",
            "--no-tags",
            bundle,
            "refs/heads/candidate:refs/ac23/candidate",
        )
        _git(repository, "checkout", "--detach", "--force", manifest["head_commit"])
        status = _git(
            repository, "status", "--porcelain=v1", "-z", "--untracked-files=all"
        ).stdout
    except subprocess.CalledProcessError:
        fail("E_CLEAN_STATUS")
    if status:
        fail("E_CLEAN_STATUS")


def verify(package_root: Path, expected_repository_url: str | None = None) -> None:
    package_root = package_root.resolve()
    if not package_root.is_dir():
        fail("E_SCHEMA")
    actual_files = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_files != PACKAGE_FILES:
        fail("E_SCHEMA")
    manifest = _load_manifest(
        package_root / "IDENTITY" / "candidate_artifact_identity.json"
    )

    normalized = normalize_repository_url(manifest["repository_url"])
    if not _same(normalized, manifest["repository_url"]):
        fail("E_REPOSITORY_URL")
    if not _same(normalized, APPROVED_REPOSITORY_URL):
        fail("E_REPOSITORY_URL")
    if expected_repository_url is not None:
        expected = normalize_repository_url(expected_repository_url)
        if not _same(normalized, expected):
            fail("E_REPOSITORY_URL")
    if not _same(manifest["base_commit"], APPROVED_BASE_COMMIT):
        fail("E_BASE_OBJECT")
    if not _same(manifest["base_tree"], APPROVED_BASE_TREE):
        fail("E_BASE_TREE")
    if manifest["normative_contract_path"] != NORMATIVE_CONTRACT_PATH:
        fail("E_CONTRACT_DIGEST")
    if not _same(manifest["normative_contract_sha256"], NORMATIVE_CONTRACT_SHA256):
        fail("E_CONTRACT_DIGEST")

    paths = {
        "patch": package_root / "PATCH" / "cumulative.patch",
        "source": package_root / "SOURCE" / "candidate_source.tar",
        "changed": package_root / "IDENTITY" / "changed_paths.nul",
        "evidence": package_root / "EVIDENCE" / "evidence_raw.tar",
        "bundle": package_root / "SOURCE" / "candidate_repository.bundle",
    }
    digest_checks = (
        ("patch", "patch_sha256", "E_PATCH_DIGEST"),
        ("source", "source_archive_sha256", "E_SOURCE_DIGEST"),
        ("changed", "changed_path_manifest_sha256", "E_CHANGED_PATH_DIGEST"),
        ("evidence", "evidence_sha256", "E_EVIDENCE_DIGEST"),
    )
    for file_key, manifest_key, error_code in digest_checks:
        try:
            actual = _sha256(paths[file_key])
        except OSError:
            fail(error_code)
        if not _same(actual, manifest[manifest_key]):
            fail(error_code)

    with tempfile.TemporaryDirectory(prefix="ac23-verify-") as temporary_text:
        temporary = Path(temporary_text)
        repository, object_format = _prepare_bundle(paths["bundle"], temporary, manifest)
        _verify_objects(repository, manifest, object_format)
        _validate_evidence_tar(paths["evidence"], manifest)

        try:
            contract = _git(
                repository,
                "show",
                f"{manifest['head_commit']}:{NORMATIVE_CONTRACT_PATH}",
            ).stdout
        except subprocess.CalledProcessError:
            fail("E_CONTRACT_DIGEST")
        contract_digest = hashlib.sha256(contract).hexdigest()
        if not _same(contract_digest, manifest["normative_contract_sha256"]):
            fail("E_CONTRACT_DIGEST")

        expected_changed = _changed_paths(
            repository, manifest["base_commit"], manifest["head_commit"]
        )
        try:
            submitted_changed = paths["changed"].read_bytes()
        except OSError:
            fail("E_CHANGED_PATH_DIGEST")
        if not _same(expected_changed, submitted_changed):
            fail("E_CHANGED_PATH_DIGEST")

        patch_tree = _patch_tree(paths["bundle"], paths["patch"], temporary, manifest)
        if not _same(patch_tree, manifest["patch_applied_tree"]):
            fail("E_PATCH_TREE")

        source_tree, self_reference = _source_tree(
            paths["source"], temporary / "source-verification", object_format
        )
        if self_reference:
            fail("E_SELF_REFERENCE")
        if not _same(source_tree, manifest["source_archive_tree"]):
            fail("E_SOURCE_TREE")

        expected_tree = manifest["head_tree"]
        tree_values = (
            manifest["submitted_head_tree"],
            manifest["patch_applied_tree"],
            manifest["source_archive_tree"],
            patch_tree,
            source_tree,
        )
        if any(not _same(value, expected_tree) for value in tree_values):
            fail("E_TREE_MISMATCH")
        _checkout_clean(paths["bundle"], temporary, manifest)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Butler AC-23 candidate identity")
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--expected-repository-url")
    args = parser.parse_args(argv)
    try:
        verify(args.package_root, args.expected_repository_url)
    except VerificationError as error:
        print(
            json.dumps(
                {"ac23_pass": 0, "error_code": error.code},
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {"ac23_pass": 0, "error_code": "E_SCHEMA"},
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print('{"ac23_pass":1,"error_code":""}')
    print("AC23_PASS=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
