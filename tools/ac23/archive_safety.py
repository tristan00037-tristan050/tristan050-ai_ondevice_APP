#!/usr/bin/env python3
"""Fail-closed validation and extraction for AC-23 tar archives.

The validator deliberately does not use ``Path.resolve`` for member names:
archive paths are POSIX byte-level identifiers, not host filesystem paths.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import shutil
import sys
import tarfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_MAX_MEMBERS = 100_000
DEFAULT_MAX_MEMBER_SIZE = 1 << 30
DEFAULT_MAX_TOTAL_SIZE = 4 << 30


class ArchiveSafetyError(ValueError):
    """Raised when an archive is unsafe to inspect or extract."""


@dataclass(frozen=True)
class ArchiveLimits:
    max_members: int = DEFAULT_MAX_MEMBERS
    max_member_size: int = DEFAULT_MAX_MEMBER_SIZE
    max_total_size: int = DEFAULT_MAX_TOTAL_SIZE

    def validate(self) -> None:
        defaults = (
            (self.max_members, DEFAULT_MAX_MEMBERS),
            (self.max_member_size, DEFAULT_MAX_MEMBER_SIZE),
            (self.max_total_size, DEFAULT_MAX_TOTAL_SIZE),
        )
        if any(value <= 0 or value > maximum for value, maximum in defaults):
            raise ArchiveSafetyError("archive limit exceeds the fail-closed ceiling")


def _segments(name: str) -> tuple[str, ...]:
    if not name or "\\" in name or name.startswith("/"):
        raise ArchiveSafetyError("unsafe archive member path")
    if "\x00" in name:
        raise ArchiveSafetyError("NUL in archive member path")
    parts = tuple(name.rstrip("/").split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ArchiveSafetyError("non-canonical archive member path")
    if any(part.casefold() == ".git" for part in parts):
        raise ArchiveSafetyError("repository metadata is forbidden")
    return parts


def _collision_key(parts: Iterable[str]) -> str:
    return "/".join(unicodedata.normalize("NFC", part).casefold() for part in parts)


def _validate_symlink(parts: tuple[str, ...], target: str, root: str) -> None:
    if not target or "\\" in target or "\x00" in target or target.startswith("/"):
        raise ArchiveSafetyError("unsafe symlink target")
    target_parts = target.split("/")
    if any(part == "" for part in target_parts):
        raise ArchiveSafetyError("non-canonical symlink target")
    resolved = posixpath.normpath(posixpath.join(*parts[:-1], target))
    if resolved == "." or resolved == root or not resolved.startswith(root + "/"):
        raise ArchiveSafetyError("symlink target escapes declared root")
    if any(part == ".." for part in resolved.split("/")):
        raise ArchiveSafetyError("symlink target escapes declared root")


def inspect_tar(
    archive_path: os.PathLike[str] | str,
    *,
    allowed_roots: set[str],
    limits: ArchiveLimits = ArchiveLimits(),
) -> list[tarfile.TarInfo]:
    """Return validated members without extracting any bytes."""

    limits.validate()
    if not allowed_roots or any("/" in root or not root for root in allowed_roots):
        raise ArchiveSafetyError("invalid declared root")
    members: list[tarfile.TarInfo] = []
    exact: set[str] = set()
    folded: dict[str, str] = {}
    symlinks: set[str] = set()
    total_size = 0
    try:
        archive = tarfile.open(
            archive_path,
            mode="r:*",
            encoding="utf-8",
            errors="surrogateescape",
        )
    except (OSError, tarfile.TarError) as exc:
        raise ArchiveSafetyError("invalid tar archive") from exc
    with archive:
        for index, member in enumerate(archive):
            if index >= limits.max_members:
                raise ArchiveSafetyError("archive member limit exceeded")
            parts = _segments(member.name)
            if parts[0] not in allowed_roots:
                raise ArchiveSafetyError("undeclared archive root")
            canonical = "/".join(parts)
            if canonical in exact:
                raise ArchiveSafetyError("duplicate archive member")
            exact.add(canonical)
            collision = _collision_key(parts)
            previous = folded.get(collision)
            if previous is not None and previous != canonical:
                raise ArchiveSafetyError("casefold or Unicode archive collision")
            folded[collision] = canonical
            if any("/".join(parts[:depth]) in symlinks for depth in range(1, len(parts))):
                raise ArchiveSafetyError("archive member is nested below a symlink")
            if member.islnk() or member.ischr() or member.isblk() or member.isfifo():
                raise ArchiveSafetyError("hardlinks and special files are forbidden")
            if not (member.isdir() or member.isfile() or member.issym()):
                raise ArchiveSafetyError("unsupported archive member type")
            if member.size < 0 or member.size > limits.max_member_size:
                raise ArchiveSafetyError("archive member size limit exceeded")
            total_size += member.size
            if total_size > limits.max_total_size:
                raise ArchiveSafetyError("archive total size limit exceeded")
            if member.issym():
                _validate_symlink(parts, member.linkname, parts[0])
                symlinks.add(canonical)
            members.append(member)
    return members


def safe_extract_tar(
    archive_path: os.PathLike[str] | str,
    destination: os.PathLike[str] | str,
    *,
    allowed_roots: set[str],
    limits: ArchiveLimits = ArchiveLimits(),
) -> list[tarfile.TarInfo]:
    """Validate every member, then extract without ``extractall``."""

    members = inspect_tar(archive_path, allowed_roots=allowed_roots, limits=limits)
    destination_path = Path(destination)
    destination_path.mkdir(parents=True, exist_ok=True)
    archive = tarfile.open(
        archive_path,
        mode="r:*",
        encoding="utf-8",
        errors="surrogateescape",
    )
    with archive:
        by_name = {member.name: member for member in archive.getmembers()}
        for member in members:
            if member.issym():
                continue
            parts = _segments(member.name)
            output = destination_path.joinpath(*parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                output.mkdir(exist_ok=True)
                os.chmod(output, member.mode & 0o777)
                continue
            source = archive.extractfile(by_name[member.name])
            if source is None:
                raise ArchiveSafetyError("regular member has no payload")
            with source, output.open("xb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            os.chmod(output, member.mode & 0o777)
        for member in members:
            if not member.issym():
                continue
            parts = _segments(member.name)
            output = destination_path.joinpath(*parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(member.linkname, output)
    return members


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate an AC-23 tar before extraction")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--max-members", type=int, default=DEFAULT_MAX_MEMBERS)
    parser.add_argument("--max-member-size", type=int, default=DEFAULT_MAX_MEMBER_SIZE)
    parser.add_argument("--max-total-size", type=int, default=DEFAULT_MAX_TOTAL_SIZE)
    args = parser.parse_args()
    limits = ArchiveLimits(args.max_members, args.max_member_size, args.max_total_size)
    try:
        inspect_tar(args.archive, allowed_roots=set(args.root), limits=limits)
    except Exception:
        print(
            '{"archive_safety_pass":0,"error_code":"E_ARCHIVE_SAFETY"}',
            file=sys.stderr,
        )
        return 1
    print("ARCHIVE_SAFETY_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
