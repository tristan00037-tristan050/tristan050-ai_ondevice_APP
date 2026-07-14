from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from pathlib import Path, PurePosixPath

from .canonical import canonical_sha256
from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def build_model_manifest(root: Path, *, metadata_sha256: str, variant_id: str) -> dict[str, object]:
    root_input = root.absolute()
    if root_input.is_symlink():
        _identity_block("MODEL_ROOT_SYMLINK")
    _reject_symlink_ancestors(root_input)
    root = root_input.resolve(strict=True)
    if not root.is_dir() or not _SHA256.fullmatch(metadata_sha256) or not variant_id:
        raise GateError(FailClass.MODEL_IDENTITY_MISSING, "MODEL_ROOT_OR_METADATA", exit_code=ExitCode.SCHEMA)
    leaves: list[dict[str, object]] = []
    seen_inodes: set[tuple[int, int]] = set()
    for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        directory_path = Path(directory)
        for name in list(dirnames):
            path = directory_path / name
            if path.is_symlink():
                raise GateError(FailClass.MODEL_PATH_UNSAFE, "MODEL_SYMLINK_DIRECTORY", exit_code=ExitCode.DIGEST)
        for name in filenames:
            path = directory_path / name
            leaves.append(_hash_leaf(root, path, seen_inodes))
    leaves.sort(key=lambda leaf: str(leaf["relative_path"]).encode("utf-16be"))
    if not leaves:
        raise GateError(FailClass.MODEL_IDENTITY_MISSING, "MODEL_EMPTY", exit_code=ExitCode.SCHEMA)
    payload: dict[str, object] = {
        "schema_version": "butler.model-tier-b.model-manifest.v2.8",
        "variant_id": variant_id,
        "metadata_sha256": metadata_sha256,
        "leaves": leaves,
    }
    names = [str(leaf["relative_path"]).casefold() for leaf in leaves]
    if not any("config" in name for name in names) or not any(("tokenizer" in name or "vocab" in name) for name in names):
        _identity_block("TOKENIZER_OR_CONFIG_OMITTED")
    payload["model_manifest_sha256"] = canonical_sha256(payload)
    return payload


def _hash_leaf(root: Path, path: Path, seen: set[tuple[int, int]]) -> dict[str, object]:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        raise GateError(FailClass.MODEL_PATH_UNSAFE, "MODEL_PATH_ESCAPE", exit_code=ExitCode.DIGEST) from None
    normalized = unicodedata.normalize("NFC", relative)
    pure = PurePosixPath(normalized)
    if normalized != relative or pure.is_absolute() or ".." in pure.parts or normalized in {"", "."}:
        raise GateError(FailClass.MODEL_PATH_UNSAFE, "MODEL_RELATIVE_PATH", exit_code=ExitCode.DIGEST)
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise GateError(FailClass.MODEL_PATH_UNSAFE, "MODEL_NOT_REGULAR", exit_code=ExitCode.DIGEST)
    inode = (before.st_dev, before.st_ino)
    if before.st_nlink != 1 or inode in seen:
        raise GateError(FailClass.MODEL_PATH_UNSAFE, "MODEL_HARDLINK", exit_code=ExitCode.DIGEST)
    if before.st_size > 0 and hasattr(before, "st_blocks") and before.st_blocks * 512 < before.st_size:
        raise GateError(FailClass.MODEL_PATH_UNSAFE, "MODEL_SPARSE_FILE", exit_code=ExitCode.DIGEST)
    seen.add(inode)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise GateError(FailClass.MODEL_PATH_UNSAFE, "MODEL_OPEN_FAILED", exit_code=ExitCode.DIGEST) from None
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise GateError(FailClass.MODEL_SWAP, "MODEL_LSTAT_FSTAT", exit_code=ExitCode.DIGEST)
        digest = hashlib.sha256()
        prefix = bytearray()
        while chunk := os.read(descriptor, 1024 * 1024):
            if len(prefix) < 256:
                prefix.extend(chunk[: 256 - len(prefix)])
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns
        ):
            raise GateError(FailClass.MODEL_SWAP, "MODEL_CHANGED_DURING_HASH", exit_code=ExitCode.DIGEST)
    finally:
        os.close(descriptor)
    if bytes(prefix).startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise GateError(FailClass.PROVENANCE, "LFS_POINTER_NOT_MATERIALIZED", exit_code=ExitCode.DIGEST)
    return {
        "relative_path": normalized,
        "size_bytes": before.st_size,
        "mode": format(stat.S_IFREG | stat.S_IMODE(before.st_mode), "06o"),
        "sha256": digest.hexdigest(),
    }


def verify_model_manifest(root: Path, approved: dict[str, object]) -> str:
    required = {"schema_version", "variant_id", "metadata_sha256", "leaves", "model_manifest_sha256"}
    if set(approved) != required or approved.get("schema_version") != "butler.model-tier-b.model-manifest.v2.8":
        raise GateError(FailClass.SCHEMA_INVALID, "MODEL_MANIFEST_KEYS", exit_code=ExitCode.SCHEMA)
    declared = approved["model_manifest_sha256"]
    if not isinstance(declared, str) or not _SHA256.fullmatch(declared):
        raise GateError(FailClass.MODEL_IDENTITY_MISSING, "MODEL_MANIFEST_DIGEST", exit_code=ExitCode.SCHEMA)
    _validate_manifest_leaves(approved["leaves"])
    without_digest = {key: value for key, value in approved.items() if key != "model_manifest_sha256"}
    if canonical_sha256(without_digest) != declared:
        raise GateError(FailClass.MODEL_MANIFEST_MISMATCH, "MODEL_DECLARED_DIGEST", exit_code=ExitCode.DIGEST)
    rebuilt = build_model_manifest(
        root,
        metadata_sha256=str(approved["metadata_sha256"]),
        variant_id=str(approved["variant_id"]),
    )
    if rebuilt != approved:
        raise GateError(FailClass.MODEL_MANIFEST_MISMATCH, "MODEL_REHASH_MISMATCH", exit_code=ExitCode.DIGEST)
    return declared


def verify_approved_identity(manifest: dict[str, object], *, variant_id: str, manifest_sha256: str) -> None:
    if not variant_id or not _SHA256.fullmatch(manifest_sha256):
        raise GateError(FailClass.MODEL_IDENTITY_MISSING, "APPROVED_IDENTITY_EMPTY", exit_code=ExitCode.SCHEMA)
    if manifest.get("variant_id") != variant_id or manifest.get("model_manifest_sha256") != manifest_sha256:
        raise GateError(FailClass.UNAPPROVED_MODEL, "REGISTRY_IDENTITY_MISMATCH", exit_code=ExitCode.DIGEST)
    if re.search(r"(?:^|[-_.])(test|fixture|mock)(?:$|[-_.])", variant_id, re.IGNORECASE):
        raise GateError(FailClass.UNAPPROVED_MODEL, "TEST_ASSET_IDENTITY", exit_code=ExitCode.DIGEST)


def _validate_manifest_leaves(leaves: object) -> None:
    if not isinstance(leaves, list) or not leaves:
        raise GateError(FailClass.MODEL_IDENTITY_MISSING, "MODEL_LEAVES_EMPTY", exit_code=ExitCode.SCHEMA)
    seen: set[str] = set()
    for leaf in leaves:
        if not isinstance(leaf, dict) or set(leaf) != {"relative_path", "size_bytes", "mode", "sha256"}:
            raise GateError(FailClass.SCHEMA_INVALID, "MODEL_LEAF_KEYS", exit_code=ExitCode.SCHEMA)
        relative = leaf["relative_path"]
        if not isinstance(relative, str):
            raise GateError(FailClass.MODEL_PATH_UNSAFE, "MODEL_LEAF_PATH_TYPE", exit_code=ExitCode.DIGEST)
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or relative in seen or unicodedata.normalize("NFC", relative) != relative:
            raise GateError(FailClass.MODEL_PATH_UNSAFE, "MODEL_LEAF_PATH", exit_code=ExitCode.SCHEMA)
        seen.add(relative)
        if not isinstance(leaf["size_bytes"], int) or leaf["size_bytes"] < 0 or not re.fullmatch(r"[0-7]{6}", leaf["mode"]):
            raise GateError(FailClass.SCHEMA_INVALID, "MODEL_LEAF_METADATA", exit_code=ExitCode.SCHEMA)
        if not isinstance(leaf["sha256"], str) or not _SHA256.fullmatch(leaf["sha256"]):
            raise GateError(FailClass.SCHEMA_INVALID, "MODEL_LEAF_DIGEST", exit_code=ExitCode.SCHEMA)


class ModelIdentityGuard:
    __slots__ = ("root", "approved", "pre_digest")

    def __init__(self, root: Path, approved: dict[str, object]) -> None:
        self.root = root
        self.approved = approved
        self.pre_digest: str | None = None

    def verify_pre_generation(self) -> str:
        self.pre_digest = verify_model_manifest(self.root, self.approved)
        return self.pre_digest

    def verify_post_generation(self) -> str:
        if self.pre_digest is None:
            raise GateError(FailClass.MODEL_IDENTITY_MISSING, "PREVERIFY_MISSING", exit_code=ExitCode.SCHEMA)
        try:
            post = verify_model_manifest(self.root, self.approved)
        except GateError as exc:
            if exc.fail_class is FailClass.MODEL_MANIFEST_MISMATCH:
                raise GateError(FailClass.MODEL_SWAP, "POST_GENERATION_REHASH", exit_code=ExitCode.DIGEST) from None
            raise
        if post != self.pre_digest:
            raise GateError(FailClass.MODEL_SWAP, "PRE_POST_DIGEST", exit_code=ExitCode.DIGEST)
        return post


def _reject_symlink_ancestors(path: Path) -> None:
    current = path
    while current != current.parent:
        if current.exists() and current.is_symlink():
            _identity_block("MODEL_ANCESTOR_SYMLINK")
        current = current.parent


def _identity_block(detail: str) -> None:
    raise GateError(FailClass.IDENTITY, detail, exit_code=ExitCode.DIGEST)
