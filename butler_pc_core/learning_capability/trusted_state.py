from __future__ import annotations

import errno
import hashlib
import os
import secrets
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .strict_json import canonical_json_bytes, load_strict_bytes


class TrustedStateError(RuntimeError):
    pass


_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_READ_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NONBLOCK", 0)
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


def _close_quietly(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _require_posix() -> None:
    if os.name != "posix":
        raise TrustedStateError("TRUST_STATE_PLATFORM_UNSUPPORTED")


def _validate_directory(metadata: os.stat_result, *, trusted_root: bool) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise TrustedStateError("TRUST_STATE_DIRECTORY_INVALID")
    if trusted_root:
        if metadata.st_uid != os.geteuid():
            raise TrustedStateError("TRUST_STATE_OWNER_INVALID")
        if stat.S_IMODE(metadata.st_mode) & 0o022:
            raise TrustedStateError("TRUST_STATE_DIRECTORY_PERMISSIONS_INVALID")


def _validate_file(
    metadata: os.stat_result,
    *,
    max_bytes: int,
    exact_mode: int = 0o600,
) -> None:
    if not stat.S_ISREG(metadata.st_mode):
        raise TrustedStateError("TRUST_STATE_FILE_TYPE_INVALID")
    if metadata.st_uid != os.geteuid():
        raise TrustedStateError("TRUST_STATE_OWNER_INVALID")
    if stat.S_IMODE(metadata.st_mode) != exact_mode:
        raise TrustedStateError("TRUST_STATE_FILE_PERMISSIONS_INVALID")
    if metadata.st_nlink != 1:
        raise TrustedStateError("TRUST_STATE_LINK_COUNT_INVALID")
    if metadata.st_size < 0 or metadata.st_size > max_bytes:
        raise TrustedStateError("TRUST_STATE_TOO_LARGE")


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise TrustedStateError("TRUST_STATE_WRITE_FAILED")
        offset += written


@dataclass
class TrustedStateSession:
    directory_fd: int
    filename: str
    max_file_bytes: int

    def _open_existing(self, filename: str | None = None) -> int:
        try:
            descriptor = os.open(
                filename or self.filename,
                _READ_FLAGS,
                dir_fd=self.directory_fd,
            )
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise TrustedStateError("TRUST_STATE_OPEN_FAILED") from exc
        try:
            _validate_file(
                os.fstat(descriptor),
                max_bytes=self.max_file_bytes,
            )
            return descriptor
        except Exception:
            _close_quietly(descriptor)
            raise

    def read_bytes_optional(self) -> bytes | None:
        try:
            descriptor = self._open_existing()
        except FileNotFoundError:
            return None
        try:
            payload = bytearray()
            while len(payload) <= self.max_file_bytes:
                chunk = os.read(
                    descriptor,
                    min(8192, self.max_file_bytes + 1 - len(payload)),
                )
                if not chunk:
                    break
                payload.extend(chunk)
            if len(payload) > self.max_file_bytes:
                raise TrustedStateError("TRUST_STATE_TOO_LARGE")
            return bytes(payload)
        except TrustedStateError:
            raise
        except OSError as exc:
            raise TrustedStateError("TRUST_STATE_READ_FAILED") from exc
        finally:
            _close_quietly(descriptor)

    def read_json_optional(self) -> dict[str, Any] | None:
        raw = self.read_bytes_optional()
        if raw is None:
            return None
        try:
            return load_strict_bytes(raw, max_bytes=self.max_file_bytes)
        except ValueError as exc:
            raise TrustedStateError("TRUST_STATE_JSON_INVALID") from exc

    def _validate_existing_target(self) -> None:
        try:
            descriptor = self._open_existing()
        except FileNotFoundError:
            return
        else:
            _close_quietly(descriptor)

    def atomic_write_json(self, value: dict[str, Any]) -> None:
        payload = canonical_json_bytes(value)
        if len(payload) > self.max_file_bytes:
            raise TrustedStateError("TRUST_STATE_TOO_LARGE")
        temporary = f".{self.filename}.{secrets.token_hex(12)}.tmp"
        descriptor = -1
        try:
            descriptor = os.open(
                temporary,
                _CREATE_FLAGS,
                0o600,
                dir_fd=self.directory_fd,
            )
            created = os.fstat(descriptor)
            _validate_file(created, max_bytes=self.max_file_bytes)
            _write_all(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1

            check_fd = self._open_existing(temporary)
            try:
                check_metadata = os.fstat(check_fd)
                checked = bytearray()
                while len(checked) <= self.max_file_bytes:
                    chunk = os.read(
                        check_fd,
                        min(8192, self.max_file_bytes + 1 - len(checked)),
                    )
                    if not chunk:
                        break
                    checked.extend(chunk)
                checked_bytes = bytes(checked)
                if checked_bytes != payload:
                    raise TrustedStateError("TRUST_STATE_TEMP_VERIFY_FAILED")
                if load_strict_bytes(
                    checked_bytes,
                    max_bytes=self.max_file_bytes,
                ) != value:
                    raise TrustedStateError("TRUST_STATE_TEMP_VERIFY_FAILED")
            finally:
                _close_quietly(check_fd)

            self._validate_existing_target()
            os.replace(
                temporary,
                self.filename,
                src_dir_fd=self.directory_fd,
                dst_dir_fd=self.directory_fd,
            )
            os.fsync(self.directory_fd)

            final_fd = self._open_existing()
            try:
                final_metadata = os.fstat(final_fd)
                final_bytes = bytearray()
                while len(final_bytes) <= self.max_file_bytes:
                    chunk = os.read(
                        final_fd,
                        min(8192, self.max_file_bytes + 1 - len(final_bytes)),
                    )
                    if not chunk:
                        break
                    final_bytes.extend(chunk)
                if (
                    final_metadata.st_dev != check_metadata.st_dev
                    or final_metadata.st_ino != check_metadata.st_ino
                    or final_metadata.st_size != check_metadata.st_size
                    or hashlib.sha256(final_bytes).digest()
                    != hashlib.sha256(payload).digest()
                ):
                    raise TrustedStateError("TRUST_STATE_FINAL_VERIFY_FAILED")
            finally:
                _close_quietly(final_fd)
        except TrustedStateError:
            raise
        except Exception as exc:
            raise TrustedStateError("TRUST_STATE_WRITE_FAILED") from exc
        finally:
            if descriptor >= 0:
                _close_quietly(descriptor)
            try:
                os.unlink(temporary, dir_fd=self.directory_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass


class TrustedStateFile:
    def __init__(
        self,
        path: Path,
        *,
        max_file_bytes: int,
        lock_timeout_seconds: float = 2.0,
    ) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise TrustedStateError("TRUST_STATE_ROOT_NOT_ABSOLUTE")
        if self.path.name in {"", ".", ".."} or "/" in self.path.name:
            raise TrustedStateError("TRUST_STATE_FILENAME_INVALID")
        self.max_file_bytes = max_file_bytes
        self.lock_timeout_seconds = lock_timeout_seconds
        self.lock_name = f"{self.path.name}.lock"

    def _open_root(self, *, create: bool) -> int:
        _require_posix()
        components = self.path.parent.parts[1:]
        descriptor = os.open("/", _DIRECTORY_FLAGS)
        try:
            for index, component in enumerate(components):
                if component in {"", ".", ".."}:
                    raise TrustedStateError("TRUST_STATE_ROOT_INVALID")
                try:
                    child = os.open(
                        component,
                        _DIRECTORY_FLAGS,
                        dir_fd=descriptor,
                    )
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    child = os.open(
                        component,
                        _DIRECTORY_FLAGS,
                        dir_fd=descriptor,
                    )
                except OSError as exc:
                    raise TrustedStateError("TRUST_STATE_ROOT_OPEN_FAILED") from exc
                _validate_directory(
                    os.fstat(child),
                    trusted_root=index == len(components) - 1,
                )
                os.close(descriptor)
                descriptor = child
            return descriptor
        except Exception:
            _close_quietly(descriptor)
            raise

    @contextmanager
    def locked(self) -> Iterator[TrustedStateSession]:
        root_fd = self._open_root(create=True)
        lock_fd = -1
        acquired = False
        try:
            for attempt in range(3):
                try:
                    lock_fd = os.open(
                        self.lock_name,
                        os.O_RDWR
                        | os.O_CREAT
                        | getattr(os, "O_NOFOLLOW", 0)
                        | getattr(os, "O_CLOEXEC", 0),
                        0o600,
                        dir_fd=root_fd,
                    )
                    break
                except FileNotFoundError as exc:
                    if attempt == 2:
                        raise TrustedStateError(
                            "TRUST_STATE_LOCK_OPEN_FAILED"
                        ) from exc
                    time.sleep(0.001)
                except OSError as exc:
                    raise TrustedStateError("TRUST_STATE_LOCK_OPEN_FAILED") from exc
            _validate_file(os.fstat(lock_fd), max_bytes=1)
            deadline = time.monotonic() + self.lock_timeout_seconds
            import fcntl

            while not acquired:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                        raise TrustedStateError("TRUST_STATE_LOCK_FAILED") from exc
                    if time.monotonic() >= deadline:
                        raise TrustedStateError("TRUST_STATE_LOCK_TIMEOUT") from exc
                    time.sleep(0.01)
            yield TrustedStateSession(
                directory_fd=root_fd,
                filename=self.path.name,
                max_file_bytes=self.max_file_bytes,
            )
        finally:
            if acquired and lock_fd >= 0:
                try:
                    import fcntl

                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            if lock_fd >= 0:
                _close_quietly(lock_fd)
            _close_quietly(root_fd)
