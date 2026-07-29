from __future__ import annotations

import hashlib
import json
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable


MAX_ENTRIES = 4_096
MAX_TOTAL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_SINGLE_FILE_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
_WINDOWS_DEVICES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class CanonicalInputError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApprovedInput:
    name: str
    sha256: str
    role: str


def _canonical_path(name: str) -> tuple[str, str]:
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or name.startswith("/")
        or name.endswith("/")
    ):
        raise CanonicalInputError("ARCHIVE_PATH_INVALID")
    parts = PurePosixPath(name).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise CanonicalInputError("ARCHIVE_PATH_INVALID")
    for part in parts:
        if part.endswith((" ", ".")) or ":" in part:
            raise CanonicalInputError("ARCHIVE_WINDOWS_PATH_INVALID")
        stem = part.split(".", 1)[0].upper()
        if stem in _WINDOWS_DEVICES:
            raise CanonicalInputError("ARCHIVE_WINDOWS_PATH_INVALID")
    normalized = unicodedata.normalize("NFC", name)
    return normalized, normalized.casefold()


def preflight_zip(source: str | Path | BinaryIO) -> tuple[str, ...]:
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CanonicalInputError("ARCHIVE_INVALID") from exc
    with archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_ENTRIES:
            raise CanonicalInputError("ARCHIVE_ENTRY_COUNT_INVALID")
        seen: set[str] = set()
        total = 0
        names: list[str] = []
        for entry in entries:
            if entry.flag_bits & 0x1:
                raise CanonicalInputError("ARCHIVE_ENCRYPTED")
            normalized, collision_key = _canonical_path(entry.filename)
            if collision_key in seen:
                raise CanonicalInputError("ARCHIVE_PATH_COLLISION")
            seen.add(collision_key)
            unix_mode = (entry.external_attr >> 16) & 0o177777
            file_type = stat.S_IFMT(unix_mode)
            if file_type not in {0, stat.S_IFREG}:
                raise CanonicalInputError("ARCHIVE_FILE_TYPE_INVALID")
            if (
                entry.file_size < 0
                or entry.file_size > MAX_SINGLE_FILE_BYTES
                or entry.compress_size < 0
            ):
                raise CanonicalInputError("ARCHIVE_ENTRY_SIZE_INVALID")
            total += entry.file_size
            if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise CanonicalInputError("ARCHIVE_TOTAL_SIZE_INVALID")
            if entry.file_size and (
                entry.compress_size == 0
                or entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise CanonicalInputError("ARCHIVE_COMPRESSION_RATIO_INVALID")
            names.append(normalized)
        return tuple(names)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_approved_inputs(policy_path: Path) -> tuple[ApprovedInput, ...]:
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CanonicalInputError("CANONICAL_INPUT_POLICY_INVALID") from exc
    if set(payload) != {"schema_version", "inputs"} or payload["schema_version"] != 1:
        raise CanonicalInputError("CANONICAL_INPUT_POLICY_INVALID")
    inputs = payload["inputs"]
    if not isinstance(inputs, list) or len(inputs) != 2:
        raise CanonicalInputError("CANONICAL_INPUT_APPROVAL_MISSING")
    approved: list[ApprovedInput] = []
    names: set[str] = set()
    roles: set[str] = set()
    for value in inputs:
        if not isinstance(value, dict) or set(value) != {
            "name",
            "role",
            "sha256",
            "approval",
        }:
            raise CanonicalInputError("CANONICAL_INPUT_POLICY_INVALID")
        name = value["name"]
        role = value["role"]
        sha256 = value["sha256"]
        if (
            value["approval"] != "APPROVED_AUDIT_INPUT"
            or not isinstance(name, str)
            or not name
            or name in names
            or role not in {"product", "algorithm"}
            or role in roles
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            raise CanonicalInputError("CANONICAL_INPUT_POLICY_INVALID")
        names.add(name)
        roles.add(role)
        approved.append(ApprovedInput(name=name, sha256=sha256, role=role))
    return tuple(sorted(approved, key=lambda value: value.role))


def verify_approved_archives(
    approved: Iterable[ApprovedInput],
    archive_root: Path,
) -> None:
    for item in approved:
        path = archive_root / item.name
        if not path.is_file() or path.is_symlink():
            raise CanonicalInputError("CANONICAL_INPUT_APPROVAL_MISSING")
        if sha256_file(path) != item.sha256:
            raise CanonicalInputError("CANONICAL_INPUT_DIGEST_MISMATCH")
        preflight_zip(path)
