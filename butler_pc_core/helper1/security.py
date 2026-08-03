"""Helper1 authorities: descriptor reads, Keychain keys, DLP and release."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text

from .contracts import (
    Citation,
    Helper1ContractError,
    TerminalLatch,
    canonical_json,
    require_digest,
    require_safe_id,
    require_uuid,
    sha256_bytes,
)

MAX_ASSET_FILE_BYTES = 8 * 1024 * 1024 * 1024
MAX_CLOSURE_FILES = 4096
_INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?\b",
        r"\bsystem\s+prompt\b",
        r"\bdeveloper\s+message\b",
        r"\b(reveal|print|repeat|dump)\b.{0,40}\b(prompt|document|context)\b",
        r"(앞|이전|위).{0,12}지시.{0,8}(무시|잊)",
        r"(시스템|개발자).{0,8}(프롬프트|메시지).{0,8}(보여|출력|공개)",
        r"(문서|원문|컨텍스트).{0,16}(전체|그대로).{0,8}(보여|출력|반복)",
    )
)


class Helper1SecurityError(RuntimeError):
    pass


def safe_relative_path(value: object) -> PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or "\\" in value
        or "\x00" in value
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        raise Helper1SecurityError("PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise Helper1SecurityError("PATH_INVALID")
    return path


def open_regular_at(root_fd: int, relative: str) -> int:
    path = safe_relative_path(relative)
    current = os.dup(root_fd)
    opened: list[int] = [current]
    try:
        for part in path.parts[:-1]:
            current = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=current,
            )
            opened.append(current)
        fd = os.open(
            path.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=current,
        )
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            raise Helper1SecurityError("FILE_NOT_REGULAR")
        return fd
    except OSError as exc:
        raise Helper1SecurityError("FILE_OPEN_FAILED") from exc
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def read_bounded_fd(fd: int, maximum: int = MAX_ASSET_FILE_BYTES) -> bytes:
    info_before = os.fstat(fd)
    if (
        not stat.S_ISREG(info_before.st_mode)
        or info_before.st_size < 0
        or info_before.st_size > maximum
    ):
        raise Helper1SecurityError("FILE_SIZE_INVALID")
    position = os.lseek(fd, 0, os.SEEK_CUR)
    os.lseek(fd, 0, os.SEEK_SET)
    data = bytearray()
    try:
        while len(data) <= maximum:
            block = os.read(fd, min(1024 * 1024, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
    finally:
        os.lseek(fd, position, os.SEEK_SET)
    info_after = os.fstat(fd)
    if (
        len(data) != info_before.st_size
        or len(data) > maximum
        or (info_before.st_dev, info_before.st_ino, info_before.st_size)
        != (info_after.st_dev, info_after.st_ino, info_after.st_size)
    ):
        raise Helper1SecurityError("FILE_READ_MISMATCH")
    return bytes(data)


@dataclass(frozen=True)
class ClosureFile:
    path: str
    bytes: int
    sha256: str

    def __post_init__(self) -> None:
        safe_relative_path(self.path)
        if isinstance(self.bytes, bool) or not isinstance(self.bytes, int) or self.bytes < 1:
            raise Helper1SecurityError("CLOSURE_FILE_SIZE_INVALID")
        require_digest(self.sha256, "CLOSURE_FILE_DIGEST_INVALID")


@dataclass(frozen=True)
class VerifiedAssetClosure:
    """An immutable manifest plus the already-open asset directory."""

    root_fd: int
    files: Mapping[str, ClosureFile]
    manifest_sha256: str
    _verified: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        info = os.fstat(self.root_fd)
        if not stat.S_ISDIR(info.st_mode):
            raise Helper1SecurityError("ASSET_ROOT_NOT_DIRECTORY")
        require_digest(self.manifest_sha256, "CLOSURE_MANIFEST_DIGEST_INVALID")
        if not self.files or len(self.files) > MAX_CLOSURE_FILES:
            raise Helper1SecurityError("CLOSURE_FILE_COUNT_INVALID")
        if set(self.files) != {record.path for record in self.files.values()}:
            raise Helper1SecurityError("CLOSURE_FILE_MAP_INVALID")
        snapshot = {
            path: ClosureFile(path=record.path, bytes=record.bytes, sha256=record.sha256)
            for path, record in self.files.items()
        }
        object.__setattr__(self, "files", MappingProxyType(snapshot))
        calculated = sha256_bytes(
            canonical_json(
                {
                    "schema_version": "butler.asset-closure.v1",
                    "files": {
                        path: {"bytes": item.bytes, "sha256": item.sha256}
                        for path, item in sorted(self.files.items())
                    },
                }
            )
        )
        if not hmac.compare_digest(calculated, self.manifest_sha256):
            raise Helper1SecurityError("CLOSURE_MANIFEST_DIGEST_MISMATCH")

    def verify_all(self) -> None:
        for path, record in sorted(self.files.items()):
            fd = open_regular_at(self.root_fd, path)
            try:
                data = read_bounded_fd(fd, maximum=record.bytes)
            finally:
                os.close(fd)
            if len(data) != record.bytes or not hmac.compare_digest(
                sha256_bytes(data), record.sha256
            ):
                raise Helper1SecurityError("ASSET_CLOSURE_MISMATCH")
        object.__setattr__(self, "_verified", True)

    def open_verified(self, relative: str) -> int:
        if not self._verified:
            raise Helper1SecurityError("ASSET_CLOSURE_NOT_VERIFIED")
        record = self.files.get(relative)
        if record is None:
            raise Helper1SecurityError("ASSET_NOT_IN_CLOSURE")
        fd = open_regular_at(self.root_fd, relative)
        try:
            data = read_bounded_fd(fd, maximum=record.bytes)
            if len(data) != record.bytes or not hmac.compare_digest(
                sha256_bytes(data), record.sha256
            ):
                raise Helper1SecurityError("ASSET_CLOSURE_MISMATCH")
            os.lseek(fd, 0, os.SEEK_SET)
            return fd
        except Exception:
            os.close(fd)
            raise

    def read_verified(self, relative: str, maximum: int = MAX_ASSET_FILE_BYTES) -> bytes:
        fd = self.open_verified(relative)
        try:
            return read_bounded_fd(fd, maximum=maximum)
        finally:
            os.close(fd)


def derive_subkey(master: bytes, label: bytes) -> bytes:
    if len(master) != 32 or not label or len(label) > 128:
        raise Helper1SecurityError("KEY_DERIVATION_INPUT_INVALID")
    return hmac.new(
        master, b"butler/helper1/subkey/v2\x00" + label, hashlib.sha256
    ).digest()


class KeyProvider(Protocol):
    is_production_provider: bool

    def key(self, workspace_id: str) -> tuple[str, bytes]: ...


@dataclass
class MemoryKeyProvider:
    """Unit-test authority. Product assembly rejects this provider."""

    root: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    is_production_provider: bool = field(default=False, init=False)

    def key(self, workspace_id: str) -> tuple[str, bytes]:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        value = hmac.new(
            self.root,
            b"butler/helper1/workspace-key/v2\x00" + workspace_id.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return "test-memory-key", value


@dataclass
class MacOSKeychainProvider:
    service: str = "com.butler.helper1.workspace-key.v2"
    is_production_provider: bool = field(default=True, init=False)

    def _account(self, workspace_id: str) -> str:
        require_uuid(workspace_id, "WORKSPACE_ID_INVALID")
        return f"workspace:{workspace_id}"

    def key(self, workspace_id: str) -> tuple[str, bytes]:
        if platform.system() != "Darwin":
            raise Helper1SecurityError("SECURE_KEY_UNAVAILABLE")
        account = self._account(workspace_id)
        try:
            found = subprocess.run(
                [
                    "/usr/bin/security",
                    "find-generic-password",
                    "-a",
                    account,
                    "-s",
                    self.service,
                    "-w",
                ],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise Helper1SecurityError("SECURE_KEY_UNAVAILABLE") from exc
        if found.returncode == 0:
            try:
                key = base64.urlsafe_b64decode(found.stdout.strip())
            except Exception as exc:
                raise Helper1SecurityError("SECURE_KEY_INVALID") from exc
            if len(key) != 32:
                raise Helper1SecurityError("SECURE_KEY_INVALID")
            return "macos-data-protection-keychain-v1", key

        key = secrets.token_bytes(32)
        try:
            added = subprocess.run(
                [
                    "/usr/bin/security",
                    "add-generic-password",
                    "-U",
                    "-a",
                    account,
                    "-s",
                    self.service,
                    "-w",
                ],
                input=base64.urlsafe_b64encode(key) + b"\n",
                check=False,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise Helper1SecurityError("SECURE_KEY_UNAVAILABLE") from exc
        if added.returncode != 0:
            raise Helper1SecurityError("SECURE_KEY_UNAVAILABLE")
        return "macos-data-protection-keychain-v1", key


def detect_prompt_injection(text: str) -> bool:
    if not isinstance(text, str):
        return True
    normalized = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f]", "", text)
    return any(pattern.search(normalized) is not None for pattern in _INJECTION_PATTERNS)
