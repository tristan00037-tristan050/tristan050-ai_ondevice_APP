from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from .errors import ExitCode, FailClass, GateError

_OID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def collect_source_provenance(
    repo: Path,
    *,
    base_ref: str,
    approved_main_ref: str,
    instrumentation_paths: tuple[str, ...],
) -> dict[str, object]:
    repo = repo.resolve(strict=True)
    if not (repo / ".git").exists():
        raise GateError(FailClass.BASE_FULL_SHA_UNRESOLVED, "NOT_GIT_REPO", exit_code=ExitCode.DIGEST)
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=all"):
        raise GateError(FailClass.DIRTY_TREE, "WORKTREE_NOT_CLEAN", exit_code=ExitCode.DIGEST)
    object_format = _git(repo, "rev-parse", "--show-object-format")
    if object_format not in {"sha1", "sha256"}:
        raise GateError(FailClass.BASE_FULL_SHA_UNRESOLVED, "OBJECT_FORMAT", exit_code=ExitCode.DIGEST)
    base_commit = _resolve(repo, f"{base_ref}^{{commit}}")
    base_tree = _resolve(repo, f"{base_commit}^{{tree}}")
    effective_commit = _resolve(repo, "HEAD^{commit}")
    effective_tree = _resolve(repo, f"{effective_commit}^{{tree}}")
    approved_commit = _resolve(repo, f"{approved_main_ref}^{{commit}}")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_commit, approved_commit],
        cwd=repo,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode
    if ancestry != 0:
        raise GateError(FailClass.BASE_NOT_APPROVED, "BASE_NOT_ANCESTOR", exit_code=ExitCode.DIGEST)
    changed = tuple(filter(None, _git(repo, "diff", "--name-only", f"{base_commit}..{effective_commit}").splitlines()))
    allowed = tuple(sorted(set(instrumentation_paths)))
    if any(path not in allowed for path in changed):
        raise GateError(FailClass.PATCH_SCOPE_MISMATCH, "INSTRUMENTATION_PATH", exit_code=ExitCode.DIGEST)
    diff = _git_bytes(repo, "diff", "--binary", "--full-index", f"{base_commit}..{effective_commit}", "--", *allowed)
    patch_payload = b"\n".join([
        base_commit.encode(), effective_commit.encode(), "\n".join(allowed).encode(), diff,
    ])
    attributes = _git(repo, "show", f"{effective_commit}:.gitattributes", allow_failure=True)
    if "export-subst" in attributes:
        raise GateError(FailClass.PROVENANCE, "EXPORT_SUBST_FORBIDDEN", exit_code=ExitCode.DIGEST)
    submodules = _git(repo, "submodule", "status", "--recursive", allow_failure=True)
    if any(line.startswith(("-", "+", "U")) for line in submodules.splitlines()):
        raise GateError(FailClass.DIGEST_MISMATCH, "SUBMODULE_STATE", exit_code=ExitCode.DIGEST)
    lfs_listing = _git(repo, "lfs", "ls-files", "--all", "--long", allow_failure=True)
    lfs_paths = _git(repo, "lfs", "ls-files", "--name-only", allow_failure=True).splitlines()
    if "filter=lfs" in attributes:
        fsck = subprocess.run(
            ["git", "lfs", "fsck"], cwd=repo, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if fsck.returncode != 0:
            raise GateError(FailClass.PROVENANCE, "GIT_LFS_FSCK", exit_code=ExitCode.DIGEST)
    for relative in lfs_paths:
        path = repo / relative
        if path.is_file() and path.read_bytes()[:128].startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise GateError(FailClass.PROVENANCE, "LFS_POINTER_NOT_MATERIALIZED", exit_code=ExitCode.DIGEST)
    git_tree = _git(repo, "ls-tree", "-r", "--full-tree", effective_commit)
    return {
        "schema_version": "butler.model-tier-b.source-provenance.v2.8",
        "object_format": object_format,
        "base_subject_commit_oid": base_commit,
        "base_subject_tree_oid": base_tree,
        "effective_product_commit_oid": effective_commit,
        "effective_product_tree_oid": effective_tree,
        "harness_commit_oid": effective_commit,
        "harness_tree_oid": effective_tree,
        "approved_main_commit_oid": approved_commit,
        "instrumentation_paths": list(allowed),
        "instrumentation_patch_sha256": hashlib.sha256(patch_payload).hexdigest(),
        "submodule_status_sha256": hashlib.sha256(submodules.encode()).hexdigest(),
        "git_tree_sha256": hashlib.sha256(git_tree.encode()).hexdigest(),
        "lfs_listing_sha256": hashlib.sha256(lfs_listing.encode()).hexdigest(),
        "lfs_materialized_path_count": len(lfs_paths),
        "clean_tree": True,
        "base_is_approved_ancestor": True,
    }


def _resolve(repo: Path, ref: str) -> str:
    value = _git(repo, "rev-parse", "--verify", ref)
    if not _OID.fullmatch(value):
        raise GateError(FailClass.BASE_FULL_SHA_UNRESOLVED, "OID_LENGTH", exit_code=ExitCode.DIGEST)
    return value


def validate_full_oid(value: str, object_format: str) -> None:
    length = 40 if object_format == "sha1" else 64 if object_format == "sha256" else 0
    if length == 0 or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise GateError(FailClass.PROVENANCE, "SHORT_OR_INVALID_OID", exit_code=ExitCode.DIGEST)


def parse_lfs_pointer(data: bytes) -> dict[str, object]:
    try:
        text = data.decode("ascii")
    except UnicodeError:
        raise GateError(FailClass.PROVENANCE, "LFS_POINTER_ENCODING", exit_code=ExitCode.DIGEST) from None
    match = re.fullmatch(
        r"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([1-9][0-9]*)\n?",
        text,
    )
    if not match:
        raise GateError(FailClass.PROVENANCE, "LFS_POINTER_SCHEMA", exit_code=ExitCode.DIGEST)
    return {"object_sha256": match.group(1), "size_bytes": int(match.group(2))}


def verify_lfs_materialization(pointer: bytes, materialized: Path) -> None:
    expected = parse_lfs_pointer(pointer)
    if not materialized.is_file() or materialized.is_symlink():
        raise GateError(FailClass.PROVENANCE, "LFS_MATERIALIZED_PATH", exit_code=ExitCode.DIGEST)
    if materialized.stat().st_size != expected["size_bytes"]:
        raise GateError(FailClass.PROVENANCE, "LFS_MATERIALIZED_SIZE", exit_code=ExitCode.DIGEST)
    digest = hashlib.sha256(materialized.read_bytes()).hexdigest()
    if digest != expected["object_sha256"]:
        raise GateError(FailClass.PROVENANCE, "LFS_MATERIALIZED_DIGEST", exit_code=ExitCode.DIGEST)


def reject_git_blob_sha256_confusion(git_blob_oid: str, file_sha256: str, object_format: str) -> None:
    validate_full_oid(git_blob_oid, object_format)
    if not re.fullmatch(r"[0-9a-f]{64}", file_sha256):
        raise GateError(FailClass.PROVENANCE, "FILE_SHA256", exit_code=ExitCode.DIGEST)
    if object_format == "sha1" and git_blob_oid == file_sha256:
        raise GateError(FailClass.PROVENANCE, "GIT_BLOB_SHA_CONFUSION", exit_code=ExitCode.DIGEST)


def validate_provenance_receipt(receipt: dict[str, object]) -> None:
    keys = {
        "schema_version", "object_format", "base_commit_oid", "base_tree_oid",
        "effective_commit_oid", "effective_tree_oid", "clean_tree", "submodules",
        "lfs_objects", "git_blob_manifest_sha256", "deployment_file_manifest_sha256",
    }
    if set(receipt) != keys or receipt["schema_version"] != "butler.model-tier-b.source-provenance.v2.8":
        raise GateError(FailClass.PROVENANCE, "PROVENANCE_KEYS", exit_code=ExitCode.SCHEMA)
    object_format = str(receipt["object_format"])
    for key in ("base_commit_oid", "base_tree_oid", "effective_commit_oid", "effective_tree_oid"):
        validate_full_oid(str(receipt[key]), object_format)
    if receipt["clean_tree"] is not True:
        raise GateError(FailClass.PROVENANCE, "DIRTY_WORKTREE", exit_code=ExitCode.DIGEST)
    for key in ("git_blob_manifest_sha256", "deployment_file_manifest_sha256"):
        if not isinstance(receipt[key], str) or not re.fullmatch(r"[0-9a-f]{64}", receipt[key]):
            raise GateError(FailClass.PROVENANCE, "PROVENANCE_MANIFEST_DIGEST", exit_code=ExitCode.DIGEST)
    submodules = receipt["submodules"]
    if not isinstance(submodules, list):
        raise GateError(FailClass.PROVENANCE, "SUBMODULE_LIST", exit_code=ExitCode.SCHEMA)
    for item in submodules:
        if not isinstance(item, dict) or set(item) != {"path", "url", "commit_oid", "tree_oid", "status"}:
            raise GateError(FailClass.PROVENANCE, "SUBMODULE_KEYS", exit_code=ExitCode.SCHEMA)
        validate_full_oid(item["commit_oid"], object_format)
        validate_full_oid(item["tree_oid"], object_format)
        if item["status"] != "CLEAN":
            raise GateError(FailClass.PROVENANCE, "SUBMODULE_COMMIT_MISMATCH", exit_code=ExitCode.DIGEST)
    lfs_objects = receipt["lfs_objects"]
    if not isinstance(lfs_objects, list):
        raise GateError(FailClass.PROVENANCE, "LFS_OBJECT_LIST", exit_code=ExitCode.SCHEMA)
    for item in lfs_objects:
        if not isinstance(item, dict) or set(item) != {"path", "pointer_blob_oid", "object_sha256", "materialized_sha256", "size_bytes"}:
            raise GateError(FailClass.PROVENANCE, "LFS_OBJECT_KEYS", exit_code=ExitCode.SCHEMA)
        validate_full_oid(item["pointer_blob_oid"], object_format)
        if item["object_sha256"] != item["materialized_sha256"] or not re.fullmatch(r"[0-9a-f]{64}", item["object_sha256"]):
            raise GateError(FailClass.PROVENANCE, "LFS_MATERIALIZATION", exit_code=ExitCode.DIGEST)


def _git(repo: Path, *args: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, stdin=subprocess.DEVNULL, capture_output=True, check=False,
    )
    if result.returncode != 0 and not allow_failure:
        raise GateError(FailClass.BASE_FULL_SHA_UNRESOLVED, "GIT_COMMAND_FAILED", exit_code=ExitCode.DIGEST)
    try:
        return result.stdout.decode("utf-8", "strict").strip()
    except UnicodeError:
        raise GateError(FailClass.SENSITIVE_LOG_FINDING, "GIT_OUTPUT_ENCODING", exit_code=ExitCode.SECURITY) from None


def _git_bytes(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=repo, stdin=subprocess.DEVNULL, capture_output=True, check=False)
    if result.returncode != 0:
        raise GateError(FailClass.BASE_FULL_SHA_UNRESOLVED, "GIT_DIFF_FAILED", exit_code=ExitCode.DIGEST)
    return result.stdout
