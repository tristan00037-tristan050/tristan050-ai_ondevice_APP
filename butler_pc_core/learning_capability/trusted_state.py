from __future__ import annotations

import errno
import hashlib
import os
import secrets
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class TrustedStateError(RuntimeError):
    """Stable, content-free failure for a device-local trusted state file."""


_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_CREATE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)


def _is_supported() -> bool:
    return os.name == "posix" and bool(getattr(os, "O_NOFOLLOW", 0))


def _validate_owned_mode(info: os.stat_result, *, directory: bool) -> None:
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode):
        raise TrustedStateError(
            "TRUST_STATE_DIRECTORY_INVALID" if directory else "TRUST_STATE_FILE_INVALID"
        )
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise TrustedStateError("TRUST_STATE_OWNER_INVALID")
    if info.st_mode & 0o022:
        raise TrustedStateError("TRUST_STATE_WRITABLE_BY_OTHERS")
    if not directory and stat.S_IMODE(info.st_mode) != 0o600:
        raise TrustedStateError("TRUST_STATE_MODE_INVALID")
    if not directory and info.st_nlink != 1:
        raise TrustedStateError("TRUST_STATE_LINK_COUNT_INVALID")


def _read_limited(descriptor: int, maximum: int) -> bytes:
    chunks: list[bytes] = []
    remaining = maximum + 1
    while remaining:
        chunk = os.read(descriptor, min(remaining, 8192))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    value = b"".join(chunks)
    if len(value) > maximum:
        raise TrustedStateError("TRUST_STATE_TOO_LARGE")
    return value


def _open_absolute_directory(path: Path, *, validate_final: bool) -> int:
    """Walk an absolute path one component at a time without following links."""
    if not path.is_absolute():
        raise TrustedStateError("TRUST_STATE_PATH_INVALID")
    descriptor = os.open("/", _DIRECTORY_FLAGS)
    try:
        parts = path.parts[1:]
        for index, component in enumerate(parts):
            try:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise TrustedStateError(
                        "TRUST_STATE_SYMLINK_FORBIDDEN"
                    ) from exc
                raise
            os.close(descriptor)
            descriptor = child
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode):
                raise TrustedStateError("TRUST_STATE_DIRECTORY_INVALID")
            if validate_final and index == len(parts) - 1:
                _validate_owned_mode(info, directory=True)
        if not parts and validate_final:
            _validate_owned_mode(os.fstat(descriptor), directory=True)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


class PosixTrustedStateFile:
    """Descriptor-relative trusted state storage with crash-consistent replacement."""

    def __init__(
        self,
        path: Path,
        *,
        maximum_bytes: int,
        lock_timeout_seconds: float = 2.0,
    ) -> None:
        if not _is_supported():
            raise TrustedStateError("TRUST_STATE_PLATFORM_UNSUPPORTED")
        if not path.is_absolute() or path.name in {"", ".", ".."}:
            raise TrustedStateError("TRUST_STATE_PATH_INVALID")
        self.path = path
        self.maximum_bytes = maximum_bytes
        self.lock_timeout_seconds = lock_timeout_seconds
        self._root = path.parent
        self._name = path.name
        self._lock_name = f"{path.name}.lock"

    def _open_root(self) -> int:
        try:
            descriptor = _open_absolute_directory(
                self._root,
                validate_final=True,
            )
        except FileNotFoundError:
            parent = self._root.parent
            parent_descriptor = _open_absolute_directory(
                parent,
                validate_final=True,
            )
            try:
                os.mkdir(self._root.name, mode=0o700, dir_fd=parent_descriptor)
            except FileExistsError:
                pass
            finally:
                os.close(parent_descriptor)
            descriptor = _open_absolute_directory(
                self._root,
                validate_final=True,
            )
        except OSError as exc:
            raise TrustedStateError("TRUST_STATE_ROOT_UNAVAILABLE") from exc
        return descriptor

    @contextmanager
    def locked_root(self) -> Iterator[int]:
        root_descriptor = self._open_root()
        lock_descriptor: int | None = None
        acquired = False
        try:
            try:
                lock_descriptor = os.open(
                    self._lock_name,
                    os.O_RDWR
                    | os.O_CREAT
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=root_descriptor,
                )
                _validate_owned_mode(os.fstat(lock_descriptor), directory=False)
            except OSError as exc:
                raise TrustedStateError("TRUST_STATE_LOCK_INVALID") from exc
            import fcntl

            deadline = time.monotonic() + self.lock_timeout_seconds
            while not acquired:
                try:
                    fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise TrustedStateError("TRUST_STATE_LOCK_TIMEOUT") from exc
                    time.sleep(0.01)
            yield root_descriptor
        finally:
            if lock_descriptor is not None:
                if acquired:
                    try:
                        import fcntl

                        fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
                    except OSError:
                        pass
                os.close(lock_descriptor)
            os.close(root_descriptor)

    def read(self, root_descriptor: int) -> bytes | None:
        try:
            descriptor = os.open(self._name, _READ_FLAGS, dir_fd=root_descriptor)
        except FileNotFoundError:
            return None
        except OSError as exc:
            if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise TrustedStateError("TRUST_STATE_SYMLINK_FORBIDDEN") from exc
            raise TrustedStateError("TRUST_STATE_READ_FAILED") from exc
        try:
            _validate_owned_mode(os.fstat(descriptor), directory=False)
            return _read_limited(descriptor, self.maximum_bytes)
        finally:
            os.close(descriptor)

    def replace(self, root_descriptor: int, payload: bytes) -> None:
        if len(payload) > self.maximum_bytes:
            raise TrustedStateError("TRUST_STATE_TOO_LARGE")
        temporary = f".{self._name}.{secrets.token_hex(16)}.tmp"
        descriptor: int | None = None
        replaced = False
        try:
            descriptor = os.open(
                temporary,
                _CREATE_FLAGS,
                0o600,
                dir_fd=root_descriptor,
            )
            offset = 0
            while offset < len(payload):
                offset += os.write(descriptor, payload[offset:])
            os.fsync(descriptor)
            before = os.fstat(descriptor)
            _validate_owned_mode(before, directory=False)
            os.close(descriptor)
            descriptor = None

            verify = os.open(temporary, _READ_FLAGS, dir_fd=root_descriptor)
            try:
                _validate_owned_mode(os.fstat(verify), directory=False)
                reread = _read_limited(verify, self.maximum_bytes)
            finally:
                os.close(verify)
            if not secrets.compare_digest(
                hashlib.sha256(reread).digest(),
                hashlib.sha256(payload).digest(),
            ):
                raise TrustedStateError("TRUST_STATE_TEMP_VERIFY_FAILED")

            os.replace(
                temporary,
                self._name,
                src_dir_fd=root_descriptor,
                dst_dir_fd=root_descriptor,
            )
            replaced = True
            os.fsync(root_descriptor)

            final = os.open(self._name, _READ_FLAGS, dir_fd=root_descriptor)
            try:
                after = os.fstat(final)
                _validate_owned_mode(after, directory=False)
                final_payload = _read_limited(final, self.maximum_bytes)
            finally:
                os.close(final)
            if (
                before.st_dev != after.st_dev
                or before.st_ino != after.st_ino
                or not secrets.compare_digest(
                    hashlib.sha256(final_payload).digest(),
                    hashlib.sha256(payload).digest(),
                )
            ):
                raise TrustedStateError("TRUST_STATE_FINAL_VERIFY_FAILED")
        except TrustedStateError:
            raise
        except OSError as exc:
            raise TrustedStateError("TRUST_STATE_WRITE_FAILED") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if not replaced:
                try:
                    os.unlink(temporary, dir_fd=root_descriptor)
                except FileNotFoundError:
                    pass
