from __future__ import annotations

import base64
import contextvars
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, TypeVar

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from butler_pc_core.build_info import build_tree_oid


SCHEMA_VERSION = 4
API_SCHEMA_VERSION = "2.1.0"
MAX_TITLE_SCALARS = 256
MAX_TITLE_BYTES = 1_024
MAX_FOLDER_SCALARS = 128
MAX_FOLDER_BYTES = 512
MAX_CONTENT_BYTES = 65_536
MAX_MESSAGES_PER_CONVERSATION = 10_000
MAX_PAGE_SIZE = 100
COMMAND_REPLAY_DAYS = 30
COMMAND_PURGE_BATCH = 500
BACKUP_MIN_COUNT = 3
BACKUP_RETENTION_DAYS = 30
_KEYCHAIN_SERVICE = "com.butler.desktop.home.v2"
_VALID_ROLES = {"user", "butler"}
_VALID_TERMINALS = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}
_TERMINAL_EVENTS = {
    "MODEL_COMPLETED",
    "MODEL_FAILED",
    "MODEL_CANCELLED",
    "MODEL_TIMED_OUT",
}
_RESERVED_FOLDERS = {".", "..", "미분류", "휴지통"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")
_BIDI_CONTROLS = {
    chr(0x061C), chr(0x200E), chr(0x200F),
    *(chr(value) for value in range(0x202A, 0x202F)),
    *(chr(value) for value in range(0x2066, 0x2070)),
}

_MESSAGE_COLUMNS_V3 = (
    "workspace_id", "conversation_id", "sequence", "message_id", "role",
    "ciphertext", "content_digest", "timestamp", "source", "fact_id", "score",
)
_MESSAGE_COLUMNS_V4 = (
    "workspace_id", "conversation_id", "sequence", "message_id", "role",
    "ciphertext", "timestamp", "source", "fact_id", "score",
)
_QUARANTINE_COLUMNS_V3 = (
    "quarantine_id", "workspace_id", "entity_type", "entity_id",
    "reason_code", "content_digest", "detected_at",
)
_QUARANTINE_COLUMNS_V4 = (
    "quarantine_id", "workspace_id", "entity_type", "entity_id",
    "reason_code", "detected_at",
)
_EXACT_CORE_COLUMNS: dict[str, tuple[str, ...]] = {
    "home_meta": (
        "singleton_id", "installation_id", "workspace_id", "key_id",
        "schema_version", "created_at", "updated_at",
    ),
    "home_folders": (
        "workspace_id", "folder_id", "parent_id", "display_name",
        "normalized_name", "system_kind", "version", "created_at", "updated_at",
    ),
    "home_conversations": (
        "workspace_id", "conversation_id", "folder_id", "business_profile_id",
        "title", "title_is_custom", "version", "created_at", "updated_at",
        "deleted_at", "legacy_digest",
    ),
    "home_messages": _MESSAGE_COLUMNS_V4,
    "home_events": (
        "event_id", "sequence", "workspace_id", "conversation_id", "turn_id",
        "model_request_id", "event_type", "outcome", "error_code", "request_id",
        "actor", "actor_session_digest", "payload_digest", "created_at",
    ),
    "home_audit": (
        "audit_id", "workspace_id", "entity_type", "entity_id", "action",
        "before_digest", "after_digest", "request_id", "actor",
        "actor_session_digest", "created_at",
    ),
    "home_commands": (
        "command_id", "workspace_id", "actor_id", "operation",
        "api_schema_version", "idempotency_key", "request_digest", "status",
        "response_status", "response_headers_json", "response_body_json",
        "created_at", "expires_at",
    ),
    "home_migration_items": (
        "workspace_id", "migration_id", "conversation_id", "item_digest",
        "disposition", "completed_at",
    ),
    "home_migration_receipts": (
        "workspace_id", "migration_id", "input_digest", "id_set_digest",
        "item_count", "receipt_json", "completed_at", "command_id",
    ),
    "home_backups": (
        "backup_id", "schema_from", "schema_to", "source_db_digest",
        "backup_digest", "manifest_digest", "integrity_result", "created_at",
        "retention_state",
    ),
    "home_quarantine": _QUARANTINE_COLUMNS_V4,
}


class ValidationError(ValueError):
    pass


class ConflictError(RuntimeError):
    pass


class NotFoundError(RuntimeError):
    pass


class StorageUnavailableError(RuntimeError):
    pass


class ReadOnlyError(StorageUnavailableError):
    pass


class MigrationConflict(ConflictError):
    def __init__(self, receipt: dict[str, Any]) -> None:
        super().__init__("BLOCK_MIGRATION_CONFLICT")
        self.receipt = receipt


@dataclass(frozen=True)
class StoreLocation:
    root: Path
    database: Path
    workspace_mirror: Path
    encryption_key: Path
    instance_lock: Path
    backup_root: Path
    runtime_root: Path


@dataclass(frozen=True)
class StartupStatus:
    status: str
    read_only: bool
    mutation_allowed: bool
    model_execution_allowed: bool
    existing_conversation_count: int
    support_code: str
    checked_at: str


_T = TypeVar("_T", bound=dict[str, Any])
_PROCESS_LOCK = threading.RLock()
_PROCESS_LOCKS: dict[str, tuple[Any, int]] = {}
_COMMAND_REPLAYED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "butler_home_command_replayed", default=False,
)


def command_was_replayed() -> bool:
    """Return replay metadata for the mutation in the current request context."""
    return _COMMAND_REPLAYED.get()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _canonical(value: Any) -> str:
    def normalize(item: Any) -> Any:
        if isinstance(item, float):
            if not math.isfinite(item) or (item == 0 and math.copysign(1.0, item) < 0):
                raise ValidationError("NON_CANONICAL_NUMBER")
            if item.is_integer():
                return int(item)
        if isinstance(item, list):
            return [normalize(child) for child in item]
        if isinstance(item, dict):
            return {str(key): normalize(child) for key, child in item.items()}
        return item

    return json.dumps(
        normalize(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def _validate_uuid(value: object, code: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError(code) from exc


def _validate_safe_id(value: object, code: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise ValidationError(code)
    return value


def _validate_utc(value: object, field: str) -> str:
    if not isinstance(value, str) or not _RFC3339_UTC.fullmatch(value):
        raise ValidationError(f"INVALID_{field.upper()}")
    try:
        _parse_time(value)
    except ValueError as exc:
        raise ValidationError(f"INVALID_{field.upper()}") from exc
    return value


def _contains_forbidden_label_character(value: str) -> bool:
    return any(
        character in _BIDI_CONTROLS
        or ord(character) == 0x7F
        or ord(character) < 0x20
        or 0x80 <= ord(character) <= 0x9F
        for character in value
    )


def _normalize_label(value: object, *, folder: bool = False, system: bool = False) -> tuple[str, str]:
    code = "INVALID_FOLDER_NAME" if folder else "INVALID_TITLE"
    if not isinstance(value, str):
        raise ValidationError(code)
    display = unicodedata.normalize("NFKC", value).strip()
    scalar_limit = MAX_FOLDER_SCALARS if folder else MAX_TITLE_SCALARS
    byte_limit = MAX_FOLDER_BYTES if folder else MAX_TITLE_BYTES
    if (
        not display
        or len(display) > scalar_limit
        or len(display.encode("utf-8")) > byte_limit
        or _contains_forbidden_label_character(display)
        or (folder and ("/" in display or "\\" in display))
    ):
        raise ValidationError(code)
    normalized = display.casefold()
    if folder and not system and normalized in {item.casefold() for item in _RESERVED_FOLDERS}:
        raise ValidationError("RESERVED_FOLDER_NAME")
    return display, normalized


def _normalize_message_content(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("INVALID_MESSAGE_CONTENT")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized.encode("utf-8")) > MAX_CONTENT_BYTES:
        raise ValidationError("MESSAGE_CONTENT_TOO_LARGE")
    for character in normalized:
        codepoint = ord(character)
        if character in _BIDI_CONTROLS:
            raise ValidationError("MESSAGE_BIDI_CONTROL_FORBIDDEN")
        if codepoint == 0 or codepoint == 0x7F or (codepoint < 0x20 and character not in {"\t", "\n"}):
            raise ValidationError("MESSAGE_CONTROL_CHARACTER_FORBIDDEN")
        if 0x80 <= codepoint <= 0x9F:
            raise ValidationError("MESSAGE_CONTROL_CHARACTER_FORBIDDEN")
    return normalized


def _default_root() -> Path:
    configured = os.environ.get("BUTLER_APP_DATA_DIR", "").strip()
    if configured:
        app_data = Path(configured).expanduser()
        if not app_data.is_absolute():
            raise StorageUnavailableError("APP_DATA_DIR_NOT_ABSOLUTE")
        return app_data / "home"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "com.butler.desktop" / "home"
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return local / "Butler" / "home"
    data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return data / "butler" / "home"


def _location(path: Path | None) -> StoreLocation:
    database = Path(os.path.abspath(path.expanduser() if path else _default_root() / "home.sqlite3"))
    root = database.parent
    return StoreLocation(
        root=root,
        database=database,
        workspace_mirror=root / "workspace.id",
        encryption_key=root / "home.key",
        instance_lock=root / ".home.instance.lock",
        backup_root=root / "backups",
        runtime_root=root / "runtime",
    )


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _chmod_private(path: Path, *, directory: bool = False) -> None:
    path.chmod(0o700 if directory else 0o600)


@contextmanager
def _exclusive_install_lock(parent: Path, final_name: str) -> Iterator[None]:
    """Serialize first-install publication across processes without trusting a symlink."""
    lock_path = parent / f".{final_name}.install.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise StorageUnavailableError("HOME_INSTALL_LOCK_UNAVAILABLE") from exc
    handle = os.fdopen(descriptor, "r+b", buffering=0)
    try:
        _chmod_private(lock_path)
        _validate_owner_and_mode(lock_path, directory=False)
        if os.name == "nt":
            import msvcrt
            if lock_path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _validate_owner_and_mode(path: Path, *, directory: bool) -> None:
    details = path.lstat()
    if stat.S_ISLNK(details.st_mode):
        raise StorageUnavailableError("HOME_STORAGE_SYMLINK_FORBIDDEN")
    if directory and not stat.S_ISDIR(details.st_mode):
        raise StorageUnavailableError("HOME_STORAGE_DIRECTORY_REQUIRED")
    if not directory and not stat.S_ISREG(details.st_mode):
        raise StorageUnavailableError("HOME_STORAGE_REGULAR_FILE_REQUIRED")
    if hasattr(os, "getuid") and details.st_uid != os.getuid():
        raise StorageUnavailableError("HOME_STORAGE_OWNER_MISMATCH")
    expected = 0o700 if directory else 0o600
    if stat.S_IMODE(details.st_mode) != expected:
        raise StorageUnavailableError("HOME_STORAGE_MODE_MISMATCH")


def _validate_no_symlink_chain(path: Path) -> None:
    current = path
    candidates: list[Path] = []
    while True:
        candidates.append(current)
        if current.parent == current:
            break
        current = current.parent
    for candidate in reversed(candidates):
        try:
            if stat.S_ISLNK(candidate.lstat().st_mode):
                raise StorageUnavailableError("HOME_STORAGE_SYMLINK_FORBIDDEN")
        except FileNotFoundError:
            continue


def _exclude_from_backup(path: Path) -> None:
    if sys.platform != "darwin":
        return
    result = subprocess.run(
        ["/usr/bin/xattr", "-w", "com.apple.metadata:com_apple_backup_excludeItem", "com.apple.backupd", str(path)],
        check=False, capture_output=True, timeout=5,
    )
    if result.returncode != 0:
        raise StorageUnavailableError("BACKUP_EXCLUSION_FAILED")


def _wal_runtime_safe() -> bool:
    version = sqlite3.sqlite_version_info
    if version[:2] == (3, 44):
        return version >= (3, 44, 6)
    if version[:2] == (3, 50):
        return version >= (3, 50, 7)
    if version[:2] == (3, 51):
        return version >= (3, 51, 3)
    return version >= (3, 52, 0)


class HomeStore:
    """Canonical first-screen product store with fail-closed continuity semantics."""

    _write_lock = threading.RLock()

    def __init__(self, path: Path | None = None, *, bootstrap_new_install: bool | None = None) -> None:
        self.location = _location(path)
        self._closed = False
        self._instance_key: str | None = None
        self._key: bytes | None = None
        self.workspace_id = ""
        self.key_id: str | None = None
        self.installation_id: str | None = None
        self._startup = StartupStatus(
            status="READ_ONLY_STORAGE_GUARD_FAILED", read_only=True,
            mutation_allowed=False, model_execution_allowed=False,
            existing_conversation_count=0, support_code="HOME_UNINITIALIZED",
            checked_at=_now(),
        )
        explicit = (
            bootstrap_new_install
            if bootstrap_new_install is not None
            else (path is not None or os.environ.get("BUTLER_HOME_BOOTSTRAP_NEW_INSTALL") == "1")
        )
        self._bootstrap(bool(explicit))

    @property
    def path(self) -> Path:
        return self.location.database

    @property
    def read_only(self) -> bool:
        return self._startup.read_only

    @property
    def model_execution_allowed(self) -> bool:
        return self._startup.model_execution_allowed

    def _support_code(self, status: str) -> str:
        seed = f"{status}:{self.workspace_id or 'none'}:{self.location.root.name}"
        return f"HOME_{hashlib.sha256(seed.encode()).hexdigest()[:16].upper()}"

    def _set_status(self, status: str, *, count: int = 0) -> None:
        ready = status == "HOME_READY"
        self._startup = StartupStatus(
            status=status,
            read_only=not ready,
            mutation_allowed=ready,
            model_execution_allowed=ready,
            existing_conversation_count=count,
            support_code=self._support_code(status),
            checked_at=_now(),
        )

    def startup_status(self) -> dict[str, Any]:
        tree_oid = build_tree_oid()
        if not re.fullmatch(r"[a-f0-9]{40,64}", tree_oid):
            raise StorageUnavailableError("BUILD_TREE_IDENTITY_UNAVAILABLE")
        return {
            "schema_version": API_SCHEMA_VERSION,
            **self._startup.__dict__,
            "tree_oid": tree_oid,
        }

    def _trace_state(self) -> dict[str, bool]:
        return {
            "database": self.path.exists(),
            "wal": Path(f"{self.path}-wal").exists(),
            "shm": Path(f"{self.path}-shm").exists(),
            "journal": Path(f"{self.path}-journal").exists(),
            "workspace": self.location.workspace_mirror.exists(),
            "key": self.location.encryption_key.exists(),
            "backup": self.location.backup_root.exists() and any(self.location.backup_root.iterdir()),
        }

    def _bootstrap(self, explicit_new_install: bool) -> None:
        _validate_no_symlink_chain(self.location.root)
        root_existed = self.location.root.exists()
        traces = self._trace_state() if root_existed else {name: False for name in ("database", "wal", "shm", "journal", "workspace", "key", "backup")}
        has_trace = any(traces.values())
        if not root_existed:
            if not explicit_new_install:
                self._set_status("NEW_INSTALL_READY")
                return
            self._create_new_install_staged()
            return
        _validate_owner_and_mode(self.location.root, directory=True)
        self._acquire_instance_lock()
        _exclude_from_backup(self.location.root)

        if not has_trace:
            if not explicit_new_install:
                self._set_status("NEW_INSTALL_READY")
                return
            self._create_new_install()
            return
        if not traces["database"]:
            self._set_status("READ_ONLY_STORAGE_GUARD_FAILED")
            return
        try:
            _validate_owner_and_mode(self.path, directory=False)
            self._load_existing_authority()
        except StorageUnavailableError as exc:
            status = str(exc)
            if status not in {
                "READ_ONLY_WORKSPACE_CONFLICT", "READ_ONLY_WORKSPACE_MIRROR_MISSING",
                "READ_ONLY_KEY_MISSING", "READ_ONLY_KEY_ID_CONFLICT",
                "READ_ONLY_DB_INTEGRITY_FAILED", "MIGRATION_BLOCKED",
            }:
                status = "READ_ONLY_STORAGE_GUARD_FAILED"
            self._set_status(status, count=self._safe_conversation_count())
            return

        try:
            self._initialize_or_migrate()
        except Exception:
            # Existing bytes remain authoritative. Migration and schema-shape
            # failures never fall through to a writable HOME_READY state.
            self._set_status("MIGRATION_BLOCKED", count=self._safe_conversation_count())
            return
        self._set_status("HOME_READY", count=self._safe_conversation_count())
        self.reconcile_interrupted_requests()

    def _acquire_instance_lock(self) -> None:
        self.location.instance_lock.touch(mode=0o600, exist_ok=True)
        _chmod_private(self.location.instance_lock)
        key = str(self.location.instance_lock)
        with _PROCESS_LOCK:
            if key in _PROCESS_LOCKS:
                handle, count = _PROCESS_LOCKS[key]
                _PROCESS_LOCKS[key] = (handle, count + 1)
                self._instance_key = key
                return
            handle = self.location.instance_lock.open("r+b")
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError) as exc:
                handle.close()
                raise StorageUnavailableError("HOME_INSTANCE_ALREADY_RUNNING") from exc
            _PROCESS_LOCKS[key] = (handle, 1)
            self._instance_key = key

    def _release_instance_lock(self) -> None:
        key = self._instance_key
        if not key:
            return
        with _PROCESS_LOCK:
            current = _PROCESS_LOCKS.get(key)
            if current is None:
                return
            handle, count = current
            if count > 1:
                _PROCESS_LOCKS[key] = (handle, count - 1)
            else:
                try:
                    if os.name == "nt":
                        import msvcrt
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()
                    _PROCESS_LOCKS.pop(key, None)
        self._instance_key = None

    def _atomic_private_text(self, path: Path, value: str) -> None:
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            _chmod_private(path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def _staging_marker_payload(self, final_root: Path, workspace_id: str) -> dict[str, str]:
        return {
            "schema_version": "butler.home.install.v1",
            "final_root_digest": hashlib.sha256(str(final_root).encode("utf-8")).hexdigest(),
            "workspace_id": workspace_id,
        }

    def _discard_owned_staging(self, staging: Path, final_root: Path) -> None:
        if not staging.exists():
            return
        _validate_owner_and_mode(staging, directory=True)
        marker = staging / ".installing.json"
        _validate_owner_and_mode(marker, directory=False)
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            workspace_id = str(uuid.UUID(str(payload["workspace_id"])))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise StorageUnavailableError("HOME_INSTALL_STAGING_UNTRUSTED") from exc
        if payload != self._staging_marker_payload(final_root, workspace_id):
            raise StorageUnavailableError("HOME_INSTALL_STAGING_UNTRUSTED")
        for candidate in staging.rglob("*"):
            details = candidate.lstat()
            if stat.S_ISLNK(details.st_mode) or (hasattr(os, "getuid") and details.st_uid != os.getuid()):
                raise StorageUnavailableError("HOME_INSTALL_STAGING_UNTRUSTED")
        if sys.platform == "darwin":
            subprocess.run(
                ["/usr/bin/security", "delete-generic-password", "-a", workspace_id, "-s", _KEYCHAIN_SERVICE],
                check=False, capture_output=True, timeout=5,
            )
        shutil.rmtree(staging)

    def _create_new_install_staged(self) -> None:
        final_location = self.location
        final_root = final_location.root
        _validate_no_symlink_chain(final_root.parent)
        final_root.parent.mkdir(parents=True, exist_ok=True)
        with _exclusive_install_lock(final_root.parent, final_root.name):
            if final_root.exists():
                raise StorageUnavailableError("HOME_INSTALL_ALREADY_PUBLISHED")
            staging = final_root.with_name(f".{final_root.name}.installing")
            self._discard_owned_staging(staging, final_root)
            staging.mkdir(mode=0o700)
            _chmod_private(staging, directory=True)
            workspace_id = str(uuid.uuid4())
            self.location = _location(staging / final_location.database.name)
            self.workspace_id = workspace_id
            self.installation_id = str(uuid.uuid4())
            try:
                self._atomic_private_text(
                    staging / ".installing.json",
                    _canonical(self._staging_marker_payload(final_root, workspace_id)) + "\n",
                )
                self._acquire_instance_lock()
                _exclude_from_backup(staging)
                self._create_new_install()
                directory_fd = os.open(staging, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                os.replace(staging, final_root)
                old_instance_key = self._instance_key
                new_instance_key = str(final_location.instance_lock)
                if old_instance_key:
                    with _PROCESS_LOCK:
                        state = _PROCESS_LOCKS.pop(old_instance_key)
                        _PROCESS_LOCKS[new_instance_key] = state
                    self._instance_key = new_instance_key
                self.location = final_location
                (final_root / ".installing.json").unlink()
                parent_fd = os.open(final_root.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
            except Exception as exc:
                self._release_instance_lock()
                self.location = final_location
                if (staging / ".installing.json").exists():
                    self._discard_owned_staging(staging, final_root)
                elif staging.exists():
                    staging.rmdir()
                raise StorageUnavailableError("HOME_NEW_INSTALL_ATOMIC_FAILED") from exc

    def _create_new_install(self) -> None:
        self.workspace_id = self.workspace_id or str(uuid.uuid4())
        self.installation_id = self.installation_id or str(uuid.uuid4())
        self._atomic_private_text(self.location.workspace_mirror, self.workspace_id + "\n")
        self._key = self._load_key(create=True)
        self.key_id = hashlib.sha256(self._key).hexdigest()
        self._initialize_fresh()
        self._set_status("HOME_READY", count=0)

    def _load_workspace_mirror(self) -> str:
        path = self.location.workspace_mirror
        if not path.exists():
            raise StorageUnavailableError("READ_ONLY_WORKSPACE_MIRROR_MISSING")
        _validate_owner_and_mode(path, directory=False)
        try:
            return str(uuid.UUID(path.read_text(encoding="ascii").strip()))
        except (ValueError, UnicodeError, OSError) as exc:
            raise StorageUnavailableError("READ_ONLY_WORKSPACE_CONFLICT") from exc

    def _keychain_lookup(self, workspace_id: str) -> bytes | None:
        lookup = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-a", workspace_id, "-s", _KEYCHAIN_SERVICE, "-w"],
            check=False, capture_output=True, timeout=5,
        )
        if lookup.returncode != 0:
            return None
        try:
            key = base64.urlsafe_b64decode(lookup.stdout.strip())
        except Exception as exc:
            raise StorageUnavailableError("HOME_KEY_VALUE_INVALID") from exc
        if len(key) != 32:
            raise StorageUnavailableError("HOME_KEY_VALUE_INVALID")
        return key

    def _load_key(self, *, create: bool) -> bytes:
        # Headless browser CI cannot access a logged-in macOS keychain. This
        # explicit non-production switch keeps the key inside the isolated E2E
        # app-data root; production builds can never select it.
        e2e_file_key = (
            os.environ.get("BUTLER_HOME_E2E_FILE_KEY") == "1"
            and os.environ.get("BUTLER_PRODUCTION", "0") != "1"
        )
        if sys.platform == "darwin" and not e2e_file_key:
            key = self._keychain_lookup(self.workspace_id)
            if key is not None:
                return key
            if not create:
                raise StorageUnavailableError("READ_ONLY_KEY_MISSING")
            key = AESGCM.generate_key(bit_length=256)
            encoded = base64.urlsafe_b64encode(key).decode("ascii")
            created = subprocess.run(
                ["/usr/bin/security", "add-generic-password", "-a", self.workspace_id, "-s", _KEYCHAIN_SERVICE, "-w", encoded, "-U"],
                check=False, capture_output=True, timeout=5,
            )
            if created.returncode != 0:
                raise StorageUnavailableError("HOME_KEYCHAIN_WRITE_FAILED")
            return key
        path = self.location.encryption_key
        if path.exists():
            _validate_owner_and_mode(path, directory=False)
            try:
                key = base64.urlsafe_b64decode(path.read_bytes())
            except Exception as exc:
                raise StorageUnavailableError("HOME_KEY_VALUE_INVALID") from exc
            if len(key) != 32:
                raise StorageUnavailableError("HOME_KEY_VALUE_INVALID")
            return key
        if not create:
            raise StorageUnavailableError("READ_ONLY_KEY_MISSING")
        if os.environ.get("BUTLER_PRODUCTION", "0") == "1":
            raise StorageUnavailableError("HOME_PLATFORM_CREDENTIAL_REQUIRED")
        key = AESGCM.generate_key(bit_length=256)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(base64.urlsafe_b64encode(key))
            handle.flush()
            os.fsync(handle.fileno())
        return key

    def _read_db_authority(self) -> tuple[str, str | None, str | None]:
        db = self._connect(read_only=True)
        try:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "home_meta" in tables:
                rows = list(db.execute("SELECT installation_id,workspace_id,key_id FROM home_meta"))
                if len(rows) != 1:
                    raise StorageUnavailableError("READ_ONLY_WORKSPACE_CONFLICT")
                return str(rows[0]["workspace_id"]), str(rows[0]["installation_id"]), str(rows[0]["key_id"])
            workspaces: set[str] = set()
            for table in ("home_folders", "home_conversations", "home_messages"):
                if table in tables:
                    workspaces.update(str(row[0]) for row in db.execute(f"SELECT DISTINCT workspace_id FROM {table}"))
            if len(workspaces) != 1:
                raise StorageUnavailableError("READ_ONLY_WORKSPACE_CONFLICT")
            return next(iter(workspaces)), None, None
        finally:
            db.close()

    def _load_existing_authority(self) -> None:
        workspace_id, installation_id, stored_key_id = self._read_db_authority()
        try:
            self.workspace_id = str(uuid.UUID(workspace_id))
        except ValueError as exc:
            raise StorageUnavailableError("READ_ONLY_WORKSPACE_CONFLICT") from exc
        self._key = self._load_key(create=False)
        derived_key_id = hashlib.sha256(self._key).hexdigest()
        if stored_key_id and stored_key_id != derived_key_id:
            self.key_id = stored_key_id
            raise StorageUnavailableError("READ_ONLY_KEY_ID_CONFLICT")
        self.key_id = derived_key_id
        self.installation_id = installation_id or str(uuid.uuid4())
        mirror = self._load_workspace_mirror()
        if mirror != self.workspace_id:
            raise StorageUnavailableError("READ_ONLY_WORKSPACE_CONFLICT")
        db = self._connect(read_only=True)
        try:
            if str(db.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
                raise StorageUnavailableError("READ_ONLY_DB_INTEGRITY_FAILED")
        finally:
            db.close()

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=10, isolation_level=None)
        else:
            db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA busy_timeout=10000")
        if not read_only:
            db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        self._assert_mutation_allowed()
        with self._write_lock:
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.execute("COMMIT")
            except Exception:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise
            finally:
                db.close()
                self._protect_database_files()

    def _assert_mutation_allowed(self) -> None:
        if self._closed or not self._startup.mutation_allowed:
            raise ReadOnlyError("HOME_READ_ONLY")

    def _protect_database_files(self) -> None:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = Path(f"{self.path}{suffix}")
            if candidate.exists():
                _chmod_private(candidate)

    def _initialize_fresh(self) -> None:
        db = self._connect()
        try:
            db.execute("BEGIN EXCLUSIVE")
            self._create_schema(db)
            now = _now()
            db.execute(
                "INSERT INTO home_meta(singleton_id,installation_id,workspace_id,key_id,schema_version,created_at,updated_at) VALUES(1,?,?,?,?,?,?)",
                (self.installation_id, self.workspace_id, self.key_id, SCHEMA_VERSION, now, now),
            )
            db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self._system_folders(db)
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
            self._protect_database_files()

    def _initialize_or_migrate(self) -> None:
        db = self._connect()
        backup: dict[str, Any] | None = None
        try:
            current = int(db.execute("PRAGMA user_version").fetchone()[0])
            if current > SCHEMA_VERSION:
                raise StorageUnavailableError("MIGRATION_BLOCKED")
            meta_version = self._meta_schema_version(db)
            if meta_version is not None and meta_version != current:
                raise StorageUnavailableError("MIGRATION_BLOCKED")
            source_shapes = self._migration_source_shapes(db)
            mode = "WAL" if _wal_runtime_safe() else "DELETE"
            actual = str(db.execute(f"PRAGMA journal_mode={mode}").fetchone()[0]).upper()
            if actual != mode:
                raise StorageUnavailableError("HOME_JOURNAL_MODE_UNAVAILABLE")
            requires_digest_removal = any(
                "content_digest" in columns for columns in source_shapes.values()
            )
            if current < SCHEMA_VERSION or requires_digest_removal:
                backup = self._create_immutable_backup(db, current, SCHEMA_VERSION)
                db.execute("BEGIN EXCLUSIVE")
                self._migrate_schema(db, current)
                db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                db.execute(
                    "UPDATE home_meta SET schema_version=?,updated_at=? WHERE singleton_id=1",
                    (SCHEMA_VERSION, _now()),
                )
                self._assert_exact_schema(db)
                if str(db.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
                    raise StorageUnavailableError("READ_ONLY_DB_INTEGRITY_FAILED")
                db.execute("COMMIT")
            else:
                db.execute("BEGIN EXCLUSIVE")
                self._create_schema(db)
                self._assert_exact_schema(db)
                if str(db.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
                    raise StorageUnavailableError("READ_ONLY_DB_INTEGRITY_FAILED")
                db.execute("COMMIT")
            if backup:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT OR IGNORE INTO home_backups(backup_id,schema_from,schema_to,source_db_digest,backup_digest,manifest_digest,integrity_result,created_at,retention_state) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        backup["backup_id"], backup["schema_from"], backup["schema_to"],
                        backup["source_db_digest"], backup["backup_digest"], backup["manifest_digest"],
                        "PASS", backup["created_at"], "KNOWN_GOOD",
                    ),
                )
                db.execute("COMMIT")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
            self._protect_database_files()

    @staticmethod
    def _table_columns(db: sqlite3.Connection, table: str) -> tuple[str, ...]:
        return tuple(str(row[1]) for row in db.execute(f"PRAGMA table_info({table})"))

    @classmethod
    def _meta_schema_version(cls, db: sqlite3.Connection) -> int | None:
        tables = {
            str(row[0]) for row in
            db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "home_meta" not in tables:
            return None
        columns = cls._table_columns(db, "home_meta")
        if columns != _EXACT_CORE_COLUMNS["home_meta"]:
            raise StorageUnavailableError("MIGRATION_BLOCKED")
        rows = list(db.execute("SELECT schema_version FROM home_meta"))
        if len(rows) != 1 or isinstance(rows[0][0], bool):
            raise StorageUnavailableError("MIGRATION_BLOCKED")
        try:
            return int(rows[0][0])
        except (TypeError, ValueError) as exc:
            raise StorageUnavailableError("MIGRATION_BLOCKED") from exc

    @classmethod
    def _migration_source_shapes(
        cls, db: sqlite3.Connection,
    ) -> dict[str, tuple[str, ...]]:
        tables = {
            str(row[0]) for row in
            db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        shapes: dict[str, tuple[str, ...]] = {}
        for table, allowed in (
            ("home_messages", {_MESSAGE_COLUMNS_V3, _MESSAGE_COLUMNS_V4}),
            ("home_quarantine", {_QUARANTINE_COLUMNS_V3, _QUARANTINE_COLUMNS_V4}),
        ):
            if table not in tables:
                continue
            columns = cls._table_columns(db, table)
            if columns not in allowed:
                raise StorageUnavailableError("MIGRATION_BLOCKED")
            shapes[table] = columns
        return shapes

    @staticmethod
    def _normalize_schema_sql(value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(
            value.replace("\n", " ").replace("\t", " ").split()
        ).casefold().replace(" if not exists ", " ")

    @classmethod
    def _schema_fingerprint(cls, db: sqlite3.Connection) -> dict[str, Any]:
        fingerprint: dict[str, Any] = {}
        for table in sorted(_EXACT_CORE_COLUMNS):
            columns = [
                tuple(row) for row in db.execute(f"PRAGMA table_info({table})")
            ]
            foreign_keys = [
                tuple(row) for row in
                db.execute(f"PRAGMA foreign_key_list({table})")
            ]
            indexes: list[dict[str, Any]] = []
            for row in db.execute(f"PRAGMA index_list({table})"):
                name = str(row[1])
                origin = str(row[3])
                definition = db.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                    (name,),
                ).fetchone()
                indexes.append({
                    "name": name if origin == "c" else None,
                    "unique": int(row[2]),
                    "origin": origin,
                    "partial": int(row[4]),
                    "columns": [
                        tuple(item[1:]) for item in
                        db.execute(f"PRAGMA index_xinfo({json.dumps(name)})")
                    ],
                    "sql": cls._normalize_schema_sql(
                        None if definition is None else definition[0]
                    ),
                })
            triggers = [
                {
                    "name": str(row[0]),
                    "sql": cls._normalize_schema_sql(row[1]),
                }
                for row in db.execute(
                    """SELECT name,sql FROM sqlite_master
                       WHERE type='trigger' AND tbl_name=? ORDER BY name""",
                    (table,),
                )
            ]
            fingerprint[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
                "indexes": sorted(
                    indexes,
                    key=lambda item: (
                        item["name"] or "",
                        item["origin"],
                        _canonical(item["columns"]),
                    ),
                ),
                "triggers": triggers,
            }
        return fingerprint

    def _assert_exact_schema(self, db: sqlite3.Connection) -> None:
        tables = {
            str(row[0]) for row in
            db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table, expected in _EXACT_CORE_COLUMNS.items():
            if table not in tables or self._table_columns(db, table) != expected:
                raise StorageUnavailableError("MIGRATION_BLOCKED")
        for table in ("home_messages", "home_quarantine"):
            if any(
                "content_digest" == column.casefold()
                for column in self._table_columns(db, table)
            ):
                raise StorageUnavailableError("MIGRATION_BLOCKED")
        reference = sqlite3.connect(":memory:", isolation_level=None)
        reference.row_factory = sqlite3.Row
        try:
            reference.execute("PRAGMA foreign_keys=ON")
            self._create_schema(reference)
            if self._schema_fingerprint(db) != self._schema_fingerprint(reference):
                raise StorageUnavailableError("MIGRATION_BLOCKED")
        finally:
            reference.close()

    def _create_immutable_backup(self, db: sqlite3.Connection, schema_from: int, schema_to: int) -> dict[str, Any]:
        self.location.backup_root.mkdir(mode=0o700, exist_ok=True)
        _chmod_private(self.location.backup_root, directory=True)
        created = _now()
        source_digest = _file_digest(self.path)
        backup_id = str(uuid.uuid4())
        backup_path = self.location.backup_root / f"home-{schema_from}-to-{schema_to}-{backup_id}.sqlite3"
        manifest_path = backup_path.with_suffix(".manifest.json")
        if backup_path.exists() or manifest_path.exists():
            raise StorageUnavailableError("BLOCK_BACKUP_OVERWRITE")
        target = sqlite3.connect(backup_path)
        try:
            db.backup(target)
            if str(target.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
                raise StorageUnavailableError("BLOCK_BACKUP_INTEGRITY")
        finally:
            target.close()
        _chmod_private(backup_path)
        backup_digest = _file_digest(backup_path)
        manifest_core = {
            "schema_version": "butler.home.backup-manifest.v1",
            "backup_id": backup_id,
            "schema_from": schema_from,
            "schema_to": schema_to,
            "source_db_digest": source_digest,
            "backup_digest": backup_digest,
            "integrity_result": "PASS",
            "created_at": created,
        }
        self._atomic_private_text(manifest_path, _canonical(manifest_core) + "\n")
        return {**manifest_core, "manifest_digest": _file_digest(manifest_path)}

    def _create_schema(self, db: sqlite3.Connection) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS home_meta(
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1), installation_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL, key_id TEXT NOT NULL, schema_version INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS home_folders(
                workspace_id TEXT NOT NULL, folder_id TEXT NOT NULL, parent_id TEXT,
                display_name TEXT NOT NULL, normalized_name TEXT NOT NULL, system_kind TEXT,
                version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(workspace_id,folder_id),
                FOREIGN KEY(workspace_id,parent_id) REFERENCES home_folders(workspace_id,folder_id))""",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_home_folder_name_v3 ON home_folders(workspace_id,COALESCE(parent_id,''),normalized_name)",
            """CREATE TABLE IF NOT EXISTS home_conversations(
                workspace_id TEXT NOT NULL, conversation_id TEXT NOT NULL, folder_id TEXT NOT NULL,
                business_profile_id TEXT, title TEXT NOT NULL, title_is_custom INTEGER NOT NULL,
                version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                deleted_at TEXT, legacy_digest TEXT, PRIMARY KEY(workspace_id,conversation_id),
                FOREIGN KEY(workspace_id,folder_id) REFERENCES home_folders(workspace_id,folder_id))""",
            "CREATE INDEX IF NOT EXISTS ix_home_conversations_page_v3 ON home_conversations(workspace_id,deleted_at,updated_at DESC,conversation_id)",
            "CREATE INDEX IF NOT EXISTS ix_home_conversations_profile_v3 ON home_conversations(workspace_id,business_profile_id,deleted_at,updated_at DESC)",
            """CREATE TABLE IF NOT EXISTS home_messages(
                workspace_id TEXT NOT NULL, conversation_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                message_id TEXT NOT NULL, role TEXT NOT NULL, ciphertext BLOB NOT NULL,
                timestamp TEXT NOT NULL, source TEXT, fact_id TEXT, score REAL,
                PRIMARY KEY(workspace_id,conversation_id,sequence), UNIQUE(workspace_id,conversation_id,message_id),
                FOREIGN KEY(workspace_id,conversation_id) REFERENCES home_conversations(workspace_id,conversation_id) ON DELETE CASCADE)""",
            """CREATE TABLE IF NOT EXISTS home_events(
                event_id TEXT PRIMARY KEY, sequence INTEGER, workspace_id TEXT NOT NULL,
                conversation_id TEXT, turn_id TEXT, model_request_id TEXT, event_type TEXT NOT NULL,
                outcome TEXT, error_code TEXT, request_id TEXT NOT NULL, actor TEXT NOT NULL,
                actor_session_digest TEXT, payload_digest TEXT NOT NULL, created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS home_audit(
                audit_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL, action TEXT NOT NULL, before_digest TEXT, after_digest TEXT,
                request_id TEXT NOT NULL, actor TEXT NOT NULL, actor_session_digest TEXT,
                created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS home_commands(
                command_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                operation TEXT NOT NULL, api_schema_version TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                request_digest TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('COMMITTED','REJECTED')),
                response_status INTEGER NOT NULL, response_headers_json TEXT NOT NULL,
                response_body_json TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                UNIQUE(workspace_id,actor_id,operation,api_schema_version,idempotency_key))""",
            "CREATE INDEX IF NOT EXISTS ix_home_commands_expiry_v3 ON home_commands(expires_at,command_id)",
            """CREATE TABLE IF NOT EXISTS home_migration_items(
                workspace_id TEXT NOT NULL, migration_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                item_digest TEXT NOT NULL, disposition TEXT NOT NULL, completed_at TEXT NOT NULL,
                PRIMARY KEY(workspace_id,migration_id,conversation_id))""",
            """CREATE TABLE IF NOT EXISTS home_migration_receipts(
                workspace_id TEXT NOT NULL, migration_id TEXT NOT NULL, input_digest TEXT NOT NULL,
                id_set_digest TEXT NOT NULL, item_count INTEGER NOT NULL, receipt_json TEXT NOT NULL,
                completed_at TEXT NOT NULL, command_id TEXT, PRIMARY KEY(workspace_id,migration_id))""",
            """CREATE TABLE IF NOT EXISTS home_backups(
                backup_id TEXT PRIMARY KEY, schema_from INTEGER NOT NULL, schema_to INTEGER NOT NULL,
                source_db_digest TEXT NOT NULL, backup_digest TEXT NOT NULL, manifest_digest TEXT NOT NULL,
                integrity_result TEXT NOT NULL, created_at TEXT NOT NULL, retention_state TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS home_quarantine(
                quarantine_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL, reason_code TEXT NOT NULL, detected_at TEXT NOT NULL)""",
            """CREATE VIRTUAL TABLE IF NOT EXISTS home_conversation_fts USING fts5(
                workspace_id UNINDEXED, conversation_id UNINDEXED, title, tokenize='unicode61')""",
        ]
        for statement in statements:
            db.execute(statement)
        for column, declaration in (
            ("sequence", "INTEGER"), ("turn_id", "TEXT"),
            ("model_request_id", "TEXT"), ("actor_session_digest", "TEXT"),
        ):
            self._ensure_column(db, "home_events", column, declaration)
        self._ensure_column(db, "home_audit", "actor_session_digest", "TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_home_event_sequence_v3 ON home_events(sequence) WHERE sequence IS NOT NULL")
        db.execute("CREATE INDEX IF NOT EXISTS ix_home_events_conversation_v3 ON home_events(workspace_id,conversation_id,sequence)")
        db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_home_terminal_v3 ON home_events(model_request_id)
            WHERE model_request_id IS NOT NULL AND event_type IN ('MODEL_COMPLETED','MODEL_FAILED','MODEL_CANCELLED','MODEL_TIMED_OUT')""")
        for trigger in (
            "CREATE TRIGGER IF NOT EXISTS home_audit_no_update BEFORE UPDATE ON home_audit BEGIN SELECT RAISE(ABORT,'HOME_AUDIT_APPEND_ONLY'); END",
            "CREATE TRIGGER IF NOT EXISTS home_audit_no_delete BEFORE DELETE ON home_audit BEGIN SELECT RAISE(ABORT,'HOME_AUDIT_APPEND_ONLY'); END",
            "CREATE TRIGGER IF NOT EXISTS home_events_no_update BEFORE UPDATE ON home_events BEGIN SELECT RAISE(ABORT,'HOME_EVENTS_APPEND_ONLY'); END",
            "CREATE TRIGGER IF NOT EXISTS home_events_no_delete BEFORE DELETE ON home_events BEGIN SELECT RAISE(ABORT,'HOME_EVENTS_APPEND_ONLY'); END",
            "CREATE TRIGGER IF NOT EXISTS home_fts_insert AFTER INSERT ON home_conversations BEGIN INSERT INTO home_conversation_fts(workspace_id,conversation_id,title) VALUES(new.workspace_id,new.conversation_id,new.title); END",
            "CREATE TRIGGER IF NOT EXISTS home_fts_update AFTER UPDATE OF title ON home_conversations BEGIN DELETE FROM home_conversation_fts WHERE workspace_id=old.workspace_id AND conversation_id=old.conversation_id; INSERT INTO home_conversation_fts(workspace_id,conversation_id,title) VALUES(new.workspace_id,new.conversation_id,new.title); END",
            "CREATE TRIGGER IF NOT EXISTS home_fts_delete AFTER DELETE ON home_conversations BEGIN DELETE FROM home_conversation_fts WHERE workspace_id=old.workspace_id AND conversation_id=old.conversation_id; END",
        ):
            db.execute(trigger)
        if int(db.execute("SELECT COUNT(*) FROM home_conversation_fts").fetchone()[0]) == 0:
            db.execute("INSERT INTO home_conversation_fts(workspace_id,conversation_id,title) SELECT workspace_id,conversation_id,title FROM home_conversations")

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _migrate_schema(self, db: sqlite3.Connection, current: int) -> None:
        self._create_schema(db)
        self._remove_unkeyed_content_digests(db)
        for column, declaration in (
            ("sequence", "INTEGER"), ("turn_id", "TEXT"), ("model_request_id", "TEXT"),
            ("actor_session_digest", "TEXT"),
        ):
            self._ensure_column(db, "home_events", column, declaration)
        rows = list(db.execute("SELECT event_id FROM home_events WHERE sequence IS NULL ORDER BY created_at,event_id"))
        next_sequence = int(db.execute("SELECT COALESCE(MAX(sequence),0) FROM home_events").fetchone()[0])
        for row in rows:
            next_sequence += 1
            db.execute("UPDATE home_events SET sequence=? WHERE event_id=?", (next_sequence, row["event_id"]))
        self._ensure_column(db, "home_migration_receipts", "command_id", "TEXT")
        now = _now()
        existing_meta = int(db.execute("SELECT COUNT(*) FROM home_meta").fetchone()[0])
        if existing_meta == 0:
            db.execute(
                "INSERT INTO home_meta VALUES(1,?,?,?,?,?,?)",
                (self.installation_id, self.workspace_id, self.key_id, SCHEMA_VERSION, now, now),
            )
        elif existing_meta == 1:
            db.execute(
                "UPDATE home_meta SET key_id=?,schema_version=?,updated_at=? WHERE singleton_id=1",
                (self.key_id, SCHEMA_VERSION, now),
            )
        else:
            raise StorageUnavailableError("READ_ONLY_WORKSPACE_CONFLICT")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "home_idempotency" in tables:
            expiry = (datetime.now(timezone.utc) + timedelta(days=COMMAND_REPLAY_DAYS)).isoformat(timespec="microseconds").replace("+00:00", "Z")
            for row in db.execute("SELECT * FROM home_idempotency"):
                created = str(row["created_at"])
                response = str(row["response_json"])
                db.execute(
                    """INSERT OR IGNORE INTO home_commands VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(uuid.uuid4()), self.workspace_id, "local-user", str(row["operation"]),
                        API_SCHEMA_VERSION, str(row["idempotency_key"]), str(row["request_digest"]),
                        "COMMITTED", 200, "{}", response, created, expiry,
                    ),
                )
            db.execute("DROP TABLE home_idempotency")
        self._system_folders(db)

    @staticmethod
    def _inventory_digest(
        db: sqlite3.Connection, table: str, columns: tuple[str, ...],
    ) -> tuple[int, str]:
        digest = hashlib.sha256()
        count = 0
        order = ",".join(columns[:3])
        for row in db.execute(
            f"SELECT {','.join(columns)} FROM {table} ORDER BY {order}"
        ):
            normalized = [
                {"bytes": bytes(value).hex()} if isinstance(value, (bytes, bytearray, memoryview))
                else value
                for value in row
            ]
            digest.update(_canonical(normalized).encode("utf-8"))
            digest.update(b"\n")
            count += 1
        return count, digest.hexdigest()

    def _remove_unkeyed_content_digests(self, db: sqlite3.Connection) -> None:
        """Copy-and-swap legacy digest-bearing variants without losing rows."""
        tables = {
            str(row[0]) for row in
            db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "home_messages" in tables:
            columns = self._table_columns(db, "home_messages")
            if columns == _MESSAGE_COLUMNS_V3:
                before = self._inventory_digest(db, "home_messages", _MESSAGE_COLUMNS_V4)
                db.execute(
                    """CREATE TABLE home_messages_v4_new(
                        workspace_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL, message_id TEXT NOT NULL,
                        role TEXT NOT NULL, ciphertext BLOB NOT NULL,
                        timestamp TEXT NOT NULL, source TEXT, fact_id TEXT, score REAL,
                        PRIMARY KEY(workspace_id,conversation_id,sequence),
                        UNIQUE(workspace_id,conversation_id,message_id),
                        FOREIGN KEY(workspace_id,conversation_id)
                          REFERENCES home_conversations(workspace_id,conversation_id)
                          ON DELETE CASCADE)"""
                )
                db.execute(
                    """INSERT INTO home_messages_v4_new(
                        workspace_id,conversation_id,sequence,message_id,role,
                        ciphertext,timestamp,source,fact_id,score)
                       SELECT workspace_id,conversation_id,sequence,message_id,role,
                        ciphertext,timestamp,source,fact_id,score FROM home_messages"""
                )
                after = self._inventory_digest(
                    db, "home_messages_v4_new", _MESSAGE_COLUMNS_V4,
                )
                if before != after:
                    raise StorageUnavailableError("MIGRATION_BLOCKED")
                db.execute("DROP TABLE home_messages")
                db.execute("ALTER TABLE home_messages_v4_new RENAME TO home_messages")
            elif columns != _MESSAGE_COLUMNS_V4:
                raise StorageUnavailableError("MIGRATION_BLOCKED")
        if "home_quarantine" in tables:
            columns = self._table_columns(db, "home_quarantine")
            if columns == _QUARANTINE_COLUMNS_V3:
                before = self._inventory_digest(
                    db, "home_quarantine", _QUARANTINE_COLUMNS_V4,
                )
                db.execute(
                    """CREATE TABLE home_quarantine_v4_new(
                        quarantine_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
                        entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
                        reason_code TEXT NOT NULL, detected_at TEXT NOT NULL)"""
                )
                db.execute(
                    """INSERT INTO home_quarantine_v4_new(
                        quarantine_id,workspace_id,entity_type,entity_id,
                        reason_code,detected_at)
                       SELECT quarantine_id,workspace_id,entity_type,entity_id,
                        reason_code,detected_at FROM home_quarantine"""
                )
                after = self._inventory_digest(
                    db, "home_quarantine_v4_new", _QUARANTINE_COLUMNS_V4,
                )
                if before != after:
                    raise StorageUnavailableError("MIGRATION_BLOCKED")
                db.execute("DROP TABLE home_quarantine")
                db.execute(
                    "ALTER TABLE home_quarantine_v4_new RENAME TO home_quarantine"
                )
            elif columns != _QUARANTINE_COLUMNS_V4:
                raise StorageUnavailableError("MIGRATION_BLOCKED")

    def _system_folders(self, db: sqlite3.Connection) -> None:
        now = _now()
        for folder_id, name, kind in (
            ("system-unclassified", "미분류", "UNCLASSIFIED"),
            ("system-trash", "휴지통", "TRASH"),
        ):
            display, normalized = _normalize_label(name, folder=True, system=True)
            db.execute(
                "INSERT OR IGNORE INTO home_folders VALUES(?,?,?,?,?,?,1,?,?)",
                (self.workspace_id, folder_id, None, display, normalized, kind, now, now),
            )

    def _safe_conversation_count(self) -> int:
        if not self.path.exists():
            return 0
        try:
            db = self._connect(read_only=True)
            try:
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "home_conversations" not in tables:
                    return 0
                if self.workspace_id:
                    return int(db.execute("SELECT COUNT(*) FROM home_conversations WHERE workspace_id=?", (self.workspace_id,)).fetchone()[0])
                return int(db.execute("SELECT COUNT(*) FROM home_conversations").fetchone()[0])
            finally:
                db.close()
        except Exception:
            return 0

    def _encrypt(self, conversation_id: str, message_id: str, content: str) -> bytes:
        if self._key is None:
            raise ReadOnlyError("HOME_READ_ONLY_KEY_UNAVAILABLE")
        nonce = os.urandom(12)
        aad = f"{self.workspace_id}:{conversation_id}:{message_id}".encode()
        return nonce + AESGCM(self._key).encrypt(nonce, content.encode("utf-8"), aad)

    def _decrypt(self, conversation_id: str, message_id: str, ciphertext: bytes) -> str:
        if self._key is None:
            raise ReadOnlyError("HOME_READ_ONLY_KEY_UNAVAILABLE")
        aad = f"{self.workspace_id}:{conversation_id}:{message_id}".encode()
        return AESGCM(self._key).decrypt(ciphertext[:12], ciphertext[12:], aad).decode("utf-8")

    @staticmethod
    def _validate_message(item: object, *, authoritative_timestamp: bool) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValidationError("INVALID_MESSAGE")
        allowed = {"id", "role", "content", "timestamp", "source", "fact_id", "score"}
        if set(item) - allowed or not {"id", "role", "content", "timestamp"}.issubset(item):
            raise ValidationError("INVALID_MESSAGE")
        message_id = _validate_safe_id(item["id"], "INVALID_MESSAGE_ID")
        role = item["role"]
        if role not in _VALID_ROLES:
            raise ValidationError("INVALID_MESSAGE_ROLE")
        content = _normalize_message_content(item["content"])
        client_timestamp = _validate_utc(item["timestamp"], "message_timestamp")
        source = item.get("source")
        if source not in (None, "factpack", "llm"):
            raise ValidationError("INVALID_MESSAGE_SOURCE")
        fact_id = item.get("fact_id")
        if fact_id is not None:
            fact_id = _validate_safe_id(fact_id, "INVALID_FACT_ID")
        score = item.get("score")
        if score is not None:
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise ValidationError("INVALID_SCORE")
            score = float(score)
            if not math.isfinite(score) or score < 0.0 or score > 1.0 or (score == 0 and math.copysign(1.0, score) < 0):
                raise ValidationError("INVALID_SCORE")
        return {
            "id": message_id, "role": role, "content": content,
            "timestamp": _now() if authoritative_timestamp else client_timestamp,
            **({"source": source} if source is not None else {}),
            **({"fact_id": fact_id} if fact_id is not None else {}),
            **({"score": score} if score is not None else {}),
        }

    @classmethod
    def _validate_legacy_conversation(cls, item: object) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValidationError("INVALID_CONVERSATION")
        allowed = {"id", "folder_id", "title", "title_is_custom", "created_at", "updated_at", "messages"}
        if set(item) - allowed or not {"id", "title", "title_is_custom", "created_at", "updated_at", "messages"}.issubset(item):
            raise ValidationError("INVALID_CONVERSATION")
        conversation_id = _validate_safe_id(item["id"], "INVALID_CONVERSATION_ID")
        title, _ = _normalize_label(item["title"])
        if not isinstance(item["title_is_custom"], bool):
            raise ValidationError("INVALID_TITLE_CUSTOM_FLAG")
        created = _validate_utc(item["created_at"], "created_at")
        updated = _validate_utc(item["updated_at"], "updated_at")
        if _parse_time(created) > _parse_time(updated):
            raise ValidationError("INVALID_TIMESTAMP_ORDER")
        messages = item["messages"]
        if not isinstance(messages, list) or len(messages) > MAX_MESSAGES_PER_CONVERSATION:
            raise ValidationError("INVALID_MESSAGES")
        validated = [cls._validate_message(message, authoritative_timestamp=False) for message in messages]
        message_ids = [message["id"] for message in validated]
        if len(message_ids) != len(set(message_ids)):
            raise ValidationError("DUPLICATE_MESSAGE_ID")
        timestamps = [_parse_time(message["timestamp"]) for message in validated]
        if timestamps != sorted(timestamps):
            raise ValidationError("INVALID_MESSAGE_TIMESTAMP_ORDER")
        return {
            "id": conversation_id, "folder_id": item.get("folder_id"), "title": title,
            "title_is_custom": item["title_is_custom"], "created_at": created,
            "updated_at": updated, "messages": validated,
        }

    def _append_message(self, db: sqlite3.Connection, conversation_id: str, message: dict[str, Any]) -> None:
        sequence = int(db.execute(
            "SELECT COALESCE(MAX(sequence),0)+1 FROM home_messages WHERE workspace_id=? AND conversation_id=?",
            (self.workspace_id, conversation_id),
        ).fetchone()[0])
        ciphertext = self._encrypt(conversation_id, message["id"], message["content"])
        db.execute(
            """INSERT INTO home_messages(
                workspace_id,conversation_id,sequence,message_id,role,ciphertext,
                timestamp,source,fact_id,score) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                self.workspace_id, conversation_id, sequence, message["id"], message["role"],
                ciphertext, message["timestamp"],
                message.get("source"), message.get("fact_id"), message.get("score"),
            ),
        )

    def _audit(
        self, db: sqlite3.Connection, entity_type: str, entity_id: str, action: str,
        before: Any, after: Any, request_id: str, actor: str, session_digest: str,
    ) -> None:
        db.execute(
            """INSERT INTO home_audit(
                audit_id,workspace_id,entity_type,entity_id,action,before_digest,after_digest,
                request_id,actor,actor_session_digest,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()), self.workspace_id, entity_type, entity_id, action,
                _digest(before) if before is not None else None,
                _digest(after) if after is not None else None,
                request_id, actor, session_digest, _now(),
            ),
        )

    def _event(
        self, db: sqlite3.Connection, conversation_id: str | None, turn_id: str | None,
        model_request_id: str | None, event_type: str, request_id: str, actor: str,
        session_digest: str, payload: Any, *, outcome: str | None = None,
        error_code: str | None = None,
    ) -> None:
        sequence = int(db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM home_events").fetchone()[0])
        db.execute(
            "INSERT INTO home_events(event_id,sequence,workspace_id,conversation_id,turn_id,model_request_id,event_type,outcome,error_code,request_id,actor,actor_session_digest,payload_digest,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()), sequence, self.workspace_id, conversation_id, turn_id,
                model_request_id, event_type, outcome, error_code, request_id, actor,
                session_digest, _digest(payload), _now(),
            ),
        )

    @staticmethod
    def _session_digest(actor: str, value: str | None) -> str:
        if value and re.fullmatch(r"[a-f0-9]{64}", value):
            return value
        return hashlib.sha256(f"session:{actor}".encode()).hexdigest()

    def _command(
        self, operation: str, idempotency_key: str, actor: str,
        request_payload: dict[str, Any], handler: Callable[[sqlite3.Connection], _T],
        *, http_status: int = 200,
    ) -> _T:
        _COMMAND_REPLAYED.set(False)
        key = _validate_uuid(idempotency_key, "INVALID_IDEMPOTENCY_KEY")
        actor_id = _validate_safe_id(actor, "INVALID_ACTOR_ID")
        request_digest = _digest(request_payload)
        with self._transaction() as db:
            row = db.execute(
                """SELECT * FROM home_commands WHERE workspace_id=? AND actor_id=? AND operation=?
                   AND api_schema_version=? AND idempotency_key=?""",
                (self.workspace_id, actor_id, operation, API_SCHEMA_VERSION, key),
            ).fetchone()
            if row:
                if row["request_digest"] != request_digest:
                    raise ConflictError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
                _COMMAND_REPLAYED.set(True)
                return json.loads(str(row["response_body_json"]))
            command_id = str(uuid.uuid4())
            created = _now()
            expires = (datetime.now(timezone.utc) + timedelta(days=COMMAND_REPLAY_DAYS)).isoformat(timespec="microseconds").replace("+00:00", "Z")
            result = handler(db)
            response_digest = _digest(result)
            command_receipt = {
                "schema_version": API_SCHEMA_VERSION,
                "command_id": command_id,
                "operation": operation,
                "idempotency_key": key,
                "request_digest": request_digest,
                "status": "COMMITTED",
                "http_status": http_status,
                "response_digest": response_digest,
                "created_at": created,
                "expires_at": expires,
                "replayed": False,
            }
            result = {**result, "command_receipt": command_receipt}
            db.execute(
                "INSERT INTO home_commands VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    command_id, self.workspace_id, actor_id, operation, API_SCHEMA_VERSION, key,
                    request_digest, "COMMITTED", http_status, "{}", _canonical(result), created, expires,
                ),
            )
            # Use the durable canonical representation for the first response
            # as well as replays, so successful retries are byte-equivalent.
            return json.loads(_canonical(result))

    def purge_command_ledger(self, *, request_id: str, idempotency_key: str, actor: str, session_digest: str | None = None) -> dict[str, Any]:
        cutoff = _now()
        session = self._session_digest(actor, session_digest)

        def mutate(db: sqlite3.Connection) -> dict[str, Any]:
            rows = list(db.execute(
                """SELECT command_id FROM home_commands c WHERE expires_at<?
                   AND NOT EXISTS(SELECT 1 FROM home_migration_receipts r WHERE r.command_id=c.command_id)
                   ORDER BY expires_at,command_id LIMIT ?""",
                (cutoff, COMMAND_PURGE_BATCH),
            ))
            for row in rows:
                db.execute("DELETE FROM home_commands WHERE command_id=?", (row["command_id"],))
            summary = {"deleted_count": len(rows), "bounded_batch": COMMAND_PURGE_BATCH, "cutoff": cutoff}
            self._audit(db, "workspace", self.workspace_id, "PURGE_COMMAND_LEDGER", None, summary, request_id, actor, session)
            return summary

        return self._command(
            "purge_command_ledger", idempotency_key, actor,
            {"method": "POST", "canonical_path": "/v1/home/commands/purge", "normalized_body": {}, "precondition_etag": None},
            mutate,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._key is not None:
            self._key = None
        self._release_instance_lock()

    def flush(self) -> None:
        if self.path.exists() and not self.read_only:
            db = self._connect()
            try:
                db.execute("PRAGMA wal_checkpoint(FULL)")
            finally:
                db.close()

    def __enter__(self) -> "HomeStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def migrate_legacy(
        self, conversations: list[dict[str, Any]], *, migration_id: str,
        request_id: str, idempotency_key: str, actor: str,
        session_digest: str | None = None,
    ) -> dict[str, Any]:
        migration = _validate_safe_id(migration_id, "INVALID_MIGRATION_ID")
        if not isinstance(conversations, list) or len(conversations) > 10_000:
            raise ValidationError("INVALID_MIGRATION_INVENTORY")
        validated = [self._validate_legacy_conversation(item) for item in conversations]
        ids = [item["id"] for item in validated]
        if len(ids) != len(set(ids)):
            raise ValidationError("DUPLICATE_CONVERSATION_ID")
        input_digest = _digest(validated)
        id_set_digest = _digest(sorted(ids))
        session = self._session_digest(actor, session_digest)
        request_payload = {
            "method": "POST",
            "canonical_path": "/v1/home/migrations/legacy-conversations",
            "normalized_body": {"migration_id": migration, "conversations": validated},
            "precondition_etag": None,
        }

        def mutate(db: sqlite3.Connection) -> dict[str, Any]:
            prior = db.execute(
                "SELECT * FROM home_migration_receipts WHERE workspace_id=? AND migration_id=?",
                (self.workspace_id, migration),
            ).fetchone()
            if prior:
                if prior["input_digest"] != input_digest or prior["id_set_digest"] != id_set_digest:
                    raise ConflictError("MIGRATION_INVENTORY_CHANGED")
                return json.loads(str(prior["receipt_json"]))
            inserted: list[dict[str, str]] = []
            identical: list[dict[str, str]] = []
            conflicts: list[dict[str, str]] = []
            now = _now()
            for item in validated:
                item_digest = _digest(item)
                item_identity = {"id": item["id"], "digest": item_digest}
                existing = db.execute(
                    "SELECT legacy_digest FROM home_conversations WHERE workspace_id=? AND conversation_id=?",
                    (self.workspace_id, item["id"]),
                ).fetchone()
                if existing:
                    if existing["legacy_digest"] == item_digest:
                        identical.append(item_identity)
                        disposition = "duplicate_exact"
                    else:
                        conflicts.append(item_identity)
                        disposition = "conflict"
                else:
                    folder_id = item.get("folder_id") or "system-unclassified"
                    if not db.execute(
                        "SELECT 1 FROM home_folders WHERE workspace_id=? AND folder_id=?",
                        (self.workspace_id, folder_id),
                    ).fetchone():
                        folder_id = "system-unclassified"
                    db.execute(
                        "INSERT INTO home_conversations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            self.workspace_id, item["id"], folder_id, None, item["title"],
                            int(item["title_is_custom"]), 1, item["created_at"], item["updated_at"],
                            None, item_digest,
                        ),
                    )
                    for message in item["messages"]:
                        self._append_message(db, item["id"], message)
                    inserted.append(item_identity)
                    disposition = "imported"
                db.execute(
                    "INSERT INTO home_migration_items VALUES(?,?,?,?,?,?)",
                    (self.workspace_id, migration, item["id"], item_digest, disposition, now),
                )
            dispositions = [
                *({"id": item["id"], "digest": item["digest"], "disposition": "imported"} for item in inserted),
                *({"id": item["id"], "digest": item["digest"], "disposition": "duplicate_exact"} for item in identical),
                *({"id": item["id"], "digest": item["digest"], "disposition": "conflict"} for item in conflicts),
            ]
            dispositions.sort(key=lambda item: item["id"])
            receipt = {
                "schema_version": "butler.home.migration.receipt.v2",
                "migration_id": migration,
                "input_digest": input_digest,
                "id_set_digest": id_set_digest,
                "item_count": len(validated),
                "disposition_count": len(dispositions),
                "disposition_root": _digest(dispositions),
                "inserted": inserted,
                "identical_existing": identical,
                "conflicts": conflicts,
                "conflict_count": len(conflicts),
                "exact_import": not conflicts and len(dispositions) == len(validated),
                "completed_at": now,
            }
            if conflicts:
                raise MigrationConflict(receipt)
            db.execute(
                "INSERT INTO home_migration_receipts(workspace_id,migration_id,input_digest,id_set_digest,item_count,receipt_json,completed_at,command_id) VALUES(?,?,?,?,?,?,?,NULL)",
                (self.workspace_id, migration, input_digest, id_set_digest, len(validated), _canonical(receipt), now),
            )
            self._audit(db, "workspace", self.workspace_id, "MIGRATE_LEGACY", None, {
                "migration_id": migration, "item_count": len(validated), "input_digest": input_digest,
            }, request_id, actor, session)
            return receipt

        result = self._command("migrate_legacy", idempotency_key, actor, request_payload, mutate)
        command_id = result.get("command_receipt", {}).get("command_id")
        if command_id:
            with self._transaction() as db:
                db.execute(
                    "UPDATE home_migration_receipts SET command_id=COALESCE(command_id,?) WHERE workspace_id=? AND migration_id=?",
                    (command_id, self.workspace_id, migration),
                )
        return result

    def snapshot(
        self, *, limit: int = 50, cursor: str | None = None,
        include_trash: bool = False, profile_id: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(limit, bool) or not 1 <= int(limit) <= MAX_PAGE_SIZE:
            raise ValidationError("INVALID_PAGE_SIZE")
        if profile_id is not None:
            profile_id = _validate_safe_id(profile_id, "INVALID_PROFILE_ID")
        if not self.path.exists():
            return {
                "schema_version": "butler.home.snapshot.v2", "workspace_id": None,
                "folders": [], "conversations": [], "next_cursor": None,
                "partial_errors": [], "read_only": True, "startup": self.startup_status(),
                "total_conversation_count": 0, "filtered_conversation_count": 0,
                "inventory_digest": _digest([]), "active_profile_filter": profile_id,
            }
        cursor_time: str | None = None
        cursor_id: str | None = None
        cursor_inventory_digest: str | None = None
        if cursor:
            try:
                decoded = json.loads(
                    base64.urlsafe_b64decode(
                        cursor + ("=" * (-len(cursor) % 4))
                    )
                )
                if (
                    not isinstance(decoded, dict)
                    or set(decoded) != {
                        "schema_version", "workspace_id", "include_trash",
                        "profile_id", "updated_at", "conversation_id",
                        "inventory_digest",
                    }
                    or decoded["schema_version"] != "butler.home.cursor.v2"
                    or decoded["workspace_id"] != self.workspace_id
                    or decoded["include_trash"] is not include_trash
                    or decoded["profile_id"] != profile_id
                ):
                    raise ValueError("cursor scope mismatch")
                cursor_time = decoded["updated_at"]
                cursor_id = decoded["conversation_id"]
                cursor_inventory_digest = decoded["inventory_digest"]
                _validate_utc(cursor_time, "cursor")
                _validate_safe_id(cursor_id, "INVALID_CURSOR")
                if (
                    not isinstance(cursor_inventory_digest, str)
                    or not re.fullmatch(r"[a-f0-9]{64}", cursor_inventory_digest)
                ):
                    raise ValueError("invalid inventory digest")
            except Exception as exc:
                raise ValidationError("INVALID_CURSOR") from exc
        db = self._connect(read_only=True)
        try:
            folder_rows = list(db.execute(
                "SELECT * FROM home_folders WHERE workspace_id=? ORDER BY COALESCE(parent_id,''),system_kind DESC,normalized_name",
                (self.workspace_id,),
            ))
            clauses = ["workspace_id=?", "deleted_at IS NOT NULL" if include_trash else "deleted_at IS NULL"]
            values: list[Any] = [self.workspace_id]
            if profile_id is not None:
                clauses.append("business_profile_id=?")
                values.append(profile_id)
            if cursor_time and cursor_id:
                clauses.append("(updated_at<? OR (updated_at=? AND conversation_id>?))")
                values.extend([cursor_time, cursor_time, cursor_id])
            rows = list(db.execute(
                f"SELECT *,(SELECT COUNT(*) FROM home_messages m WHERE m.workspace_id=home_conversations.workspace_id AND m.conversation_id=home_conversations.conversation_id) AS message_count FROM home_conversations WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC,conversation_id LIMIT ?",
                (*values, int(limit) + 1),
            ))
            total = int(db.execute(
                "SELECT COUNT(*) FROM home_conversations WHERE workspace_id=? AND " + ("deleted_at IS NOT NULL" if include_trash else "deleted_at IS NULL"),
                (self.workspace_id,),
            ).fetchone()[0])
            filtered_clauses = [
                "workspace_id=?",
                "deleted_at IS NOT NULL" if include_trash else "deleted_at IS NULL",
            ]
            filtered_values: list[Any] = [self.workspace_id]
            if profile_id is not None:
                filtered_clauses.append("business_profile_id=?")
                filtered_values.append(profile_id)
            inventory_rows = list(db.execute(
                f"""SELECT updated_at,conversation_id
                    FROM home_conversations
                    WHERE {' AND '.join(filtered_clauses)}
                    ORDER BY updated_at DESC,conversation_id""",
                filtered_values,
            ))
            filtered = len(inventory_rows)
            inventory_digest = _digest([
                [row["updated_at"], row["conversation_id"]]
                for row in inventory_rows
            ])
            if (
                cursor_inventory_digest is not None
                and cursor_inventory_digest != inventory_digest
            ):
                raise ValidationError("INVALID_CURSOR")
        finally:
            db.close()
        has_more = len(rows) > int(limit)
        rows = rows[: int(limit)]
        next_cursor = None
        if has_more and rows:
            next_cursor = base64.urlsafe_b64encode(_canonical({
                "schema_version": "butler.home.cursor.v2",
                "workspace_id": self.workspace_id,
                "include_trash": include_trash,
                "profile_id": profile_id,
                "updated_at": rows[-1]["updated_at"],
                "conversation_id": rows[-1]["conversation_id"],
                "inventory_digest": inventory_digest,
            }).encode()).decode().rstrip("=")
        conversations_out = [
            {
                "id": row["conversation_id"], "title": row["title"],
                "title_is_custom": bool(row["title_is_custom"]), "folder_id": row["folder_id"],
                "business_profile_id": row["business_profile_id"], "profile_badge": row["business_profile_id"],
                "version": row["version"], "created_at": row["created_at"], "updated_at": row["updated_at"],
                "deleted_at": row["deleted_at"], "message_count": row["message_count"], "messages": [],
                "locked": self._key is None,
            }
            for row in rows
        ]
        return {
            "schema_version": "butler.home.snapshot.v2",
            "workspace_id": self.workspace_id or None,
            "folders": [
                {
                    "folder_id": row["folder_id"], "parent_id": row["parent_id"],
                    "display_name": row["display_name"], "system_kind": row["system_kind"],
                    "version": row["version"], "created_at": row["created_at"], "updated_at": row["updated_at"],
                }
                for row in folder_rows
            ],
            "conversations": conversations_out,
            "next_cursor": next_cursor,
            "partial_errors": [],
            "read_only": self.read_only,
            "startup": self.startup_status(),
            "total_conversation_count": total,
            "filtered_conversation_count": filtered,
            "inventory_digest": inventory_digest,
            "active_profile_filter": profile_id,
        }

    def messages(self, conversation_id: str, *, after_sequence: int = 0, limit: int = 100) -> dict[str, Any]:
        conversation = _validate_safe_id(conversation_id, "INVALID_CONVERSATION_ID")
        if isinstance(after_sequence, bool) or after_sequence < 0 or isinstance(limit, bool) or not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValidationError("INVALID_PAGE")
        db = self._connect(read_only=True)
        try:
            exists = db.execute(
                """SELECT version, (
                    SELECT COUNT(*) FROM home_messages
                    WHERE workspace_id=? AND conversation_id=?
                ) AS message_count
                FROM home_conversations
                WHERE workspace_id=? AND conversation_id=?""",
                (
                    self.workspace_id, conversation, self.workspace_id, conversation,
                ),
            ).fetchone()
            if not exists:
                raise NotFoundError("CONVERSATION_NOT_FOUND")
            message_count = int(exists["message_count"])
            conversation_version = int(exists["version"])
            rows = list(db.execute(
                "SELECT * FROM home_messages WHERE workspace_id=? AND conversation_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (self.workspace_id, conversation, after_sequence, limit + 1),
            ))
        finally:
            db.close()
        if self._key is None:
            return {
                "schema_version": "butler.home.messages.v2",
                "conversation_id": conversation, "messages": [],
                "next_sequence": None, "partial_errors": [], "locked": True,
                "message_count": message_count,
                "conversation_version": conversation_version,
            }
        output: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for row in rows[:limit]:
            try:
                content = self._decrypt(conversation, row["message_id"], row["ciphertext"])
                output.append({
                    "id": row["message_id"], "role": row["role"], "content": content,
                    "timestamp": row["timestamp"], "sequence": row["sequence"],
                    **({"source": row["source"]} if row["source"] is not None else {}),
                    **({"fact_id": row["fact_id"]} if row["fact_id"] is not None else {}),
                    **({"score": row["score"]} if row["score"] is not None else {}),
                })
            except Exception:
                errors.append({"sequence": row["sequence"], "code": "MESSAGE_UNREADABLE"})
        next_sequence = rows[limit - 1]["sequence"] if len(rows) > limit else None
        return {
            "schema_version": "butler.home.messages.v2",
            "conversation_id": conversation, "messages": output,
            "next_sequence": next_sequence, "partial_errors": errors, "locked": False,
            "message_count": message_count,
            "conversation_version": conversation_version,
        }

    def search(self, query: str, *, limit: int = 50, profile_id: str | None = None) -> dict[str, Any]:
        normalized, _ = _normalize_label(query)
        if isinstance(limit, bool) or not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValidationError("INVALID_PAGE_SIZE")
        if profile_id is not None:
            profile_id = _validate_safe_id(profile_id, "INVALID_PROFILE_ID")
        tokens = [token for token in re.split(r"\s+", normalized) if token]
        fts_query = " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens)
        if not fts_query:
            return {"schema_version": "butler.home.search.v2", "conversations": []}
        db = self._connect(read_only=True)
        try:
            profile_clause = " AND c.business_profile_id=?" if profile_id is not None else ""
            parameters: list[Any] = [self.workspace_id, fts_query]
            if profile_id is not None:
                parameters.append(profile_id)
            parameters.append(limit)
            rows = list(db.execute(
                f"""SELECT c.*,(SELECT COUNT(*) FROM home_messages m WHERE m.workspace_id=c.workspace_id AND m.conversation_id=c.conversation_id) AS message_count
                    FROM home_conversation_fts f JOIN home_conversations c
                    ON c.workspace_id=f.workspace_id AND c.conversation_id=f.conversation_id
                    WHERE f.workspace_id=? AND f.title MATCH ? AND c.deleted_at IS NULL{profile_clause}
                    ORDER BY rank,c.updated_at DESC LIMIT ?""",
                parameters,
            ))
        finally:
            db.close()
        return {
            "schema_version": "butler.home.search.v2",
            "conversations": [
                {
                    "id": row["conversation_id"], "title": row["title"], "title_is_custom": bool(row["title_is_custom"]),
                    "folder_id": row["folder_id"], "business_profile_id": row["business_profile_id"],
                    "version": row["version"], "created_at": row["created_at"], "updated_at": row["updated_at"],
                    "deleted_at": row["deleted_at"], "message_count": row["message_count"], "messages": [],
                }
                for row in rows
            ],
        }

    def create_folder(
        self, name: str, *, parent_id: str | None, request_id: str,
        idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        display, normalized = _normalize_label(name, folder=True)
        if parent_id is not None:
            parent_id = _validate_safe_id(parent_id, "INVALID_PARENT_FOLDER_ID")
        session = self._session_digest(actor, session_digest)
        payload = {"name": display, "parent_id": parent_id}

        def mutate(db: sqlite3.Connection) -> dict[str, Any]:
            if parent_id and not db.execute(
                "SELECT 1 FROM home_folders WHERE workspace_id=? AND folder_id=? AND system_kind IS NULL",
                (self.workspace_id, parent_id),
            ).fetchone():
                raise NotFoundError("PARENT_FOLDER_NOT_FOUND")
            folder_id = str(uuid.uuid4())
            now = _now()
            try:
                db.execute(
                    "INSERT INTO home_folders VALUES(?,?,?,?,?,?,1,?,?)",
                    (self.workspace_id, folder_id, parent_id, display, normalized, None, now, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("DUPLICATE_FOLDER") from exc
            result = {"folder_id": folder_id, "parent_id": parent_id, "display_name": display, "system_kind": None, "version": 1, "created_at": now, "updated_at": now}
            self._audit(db, "folder", folder_id, "CREATE", None, result, request_id, actor, session)
            return result

        return self._command(
            "create_folder", idempotency_key, actor,
            {"method": "POST", "canonical_path": "/v1/home/folders", "normalized_body": payload, "precondition_etag": None},
            mutate, http_status=201,
        )

    def rename_folder(
        self, folder_id: str, name: str, expected_version: int, *, request_id: str,
        idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        folder = _validate_safe_id(folder_id, "INVALID_FOLDER_ID")
        display, normalized = _normalize_label(name, folder=True)
        session = self._session_digest(actor, session_digest)

        def mutate(db: sqlite3.Connection) -> dict[str, Any]:
            row = db.execute("SELECT * FROM home_folders WHERE workspace_id=? AND folder_id=?", (self.workspace_id, folder)).fetchone()
            if not row:
                raise NotFoundError("FOLDER_NOT_FOUND")
            if row["system_kind"]:
                raise ConflictError("SYSTEM_FOLDER_IMMUTABLE")
            if row["version"] != expected_version:
                raise ConflictError("VERSION_CONFLICT")
            version, now = expected_version + 1, _now()
            try:
                db.execute(
                    "UPDATE home_folders SET display_name=?,normalized_name=?,version=?,updated_at=? WHERE workspace_id=? AND folder_id=?",
                    (display, normalized, version, now, self.workspace_id, folder),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("DUPLICATE_FOLDER") from exc
            result = {"folder_id": folder, "parent_id": row["parent_id"], "display_name": display, "system_kind": None, "version": version, "created_at": row["created_at"], "updated_at": now}
            self._audit(db, "folder", folder, "RENAME", dict(row), result, request_id, actor, session)
            return result

        return self._command(
            "rename_folder", idempotency_key, actor,
            {"method": "PATCH", "canonical_path": f"/v1/home/folders/{folder}", "normalized_body": {"name": display}, "precondition_etag": expected_version},
            mutate,
        )

    def delete_folder(
        self, folder_id: str, expected_version: int, *, request_id: str,
        idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        folder = _validate_safe_id(folder_id, "INVALID_FOLDER_ID")
        session = self._session_digest(actor, session_digest)

        def mutate(db: sqlite3.Connection) -> dict[str, Any]:
            row = db.execute("SELECT * FROM home_folders WHERE workspace_id=? AND folder_id=?", (self.workspace_id, folder)).fetchone()
            if not row:
                raise NotFoundError("FOLDER_NOT_FOUND")
            if row["system_kind"]:
                raise ConflictError("SYSTEM_FOLDER_IMMUTABLE")
            if row["version"] != expected_version:
                raise ConflictError("VERSION_CONFLICT")
            children = int(db.execute("SELECT COUNT(*) FROM home_folders WHERE workspace_id=? AND parent_id=?", (self.workspace_id, folder)).fetchone()[0])
            conversations = int(db.execute("SELECT COUNT(*) FROM home_conversations WHERE workspace_id=? AND folder_id=?", (self.workspace_id, folder)).fetchone()[0])
            if children or conversations:
                raise ConflictError("FOLDER_NOT_EMPTY")
            db.execute("DELETE FROM home_folders WHERE workspace_id=? AND folder_id=?", (self.workspace_id, folder))
            self._audit(db, "folder", folder, "DELETE", dict(row), None, request_id, actor, session)
            return {"deleted": True, "folder_id": folder}

        return self._command(
            "delete_folder", idempotency_key, actor,
            {"method": "DELETE", "canonical_path": f"/v1/home/folders/{folder}", "normalized_body": {}, "precondition_etag": expected_version},
            mutate,
        )

    def accept_user_turn(
        self, conversation: dict[str, Any], message: dict[str, Any], *,
        business_profile_id: str | None, expected_version: int | None,
        request_id: str, idempotency_key: str, actor: str,
        session_digest: str | None = None,
    ) -> dict[str, Any]:
        allowed = {"id", "folder_id", "title", "title_is_custom", "created_at", "updated_at"}
        if not isinstance(conversation, dict) or set(conversation) != allowed:
            raise ValidationError("INVALID_CONVERSATION_COMMAND")
        conversation_id = _validate_safe_id(conversation["id"], "INVALID_CONVERSATION_ID")
        title, _ = _normalize_label(conversation["title"])
        if not isinstance(conversation["title_is_custom"], bool):
            raise ValidationError("INVALID_TITLE_CUSTOM_FLAG")
        if business_profile_id is not None:
            business_profile_id = _validate_safe_id(business_profile_id, "INVALID_PROFILE_ID")
        folder_id = conversation.get("folder_id") or "system-unclassified"
        folder_id = _validate_safe_id(folder_id, "INVALID_FOLDER_ID")
        validated_message = self._validate_message(message, authoritative_timestamp=True)
        if validated_message["role"] != "user":
            raise ValidationError("USER_TURN_ROLE_REQUIRED")
        request = _validate_uuid(request_id, "INVALID_REQUEST_ID")
        session = self._session_digest(actor, session_digest)
        normalized_body = {
            "conversation": {
                "id": conversation_id, "folder_id": folder_id, "title": title,
                "title_is_custom": conversation["title_is_custom"],
            },
            "message": {**validated_message, "timestamp": "SERVER_AUTHORITATIVE"},
            "business_profile_id": business_profile_id,
        }

        def mutate(db: sqlite3.Connection) -> dict[str, Any]:
            if not db.execute(
                "SELECT 1 FROM home_folders WHERE workspace_id=? AND folder_id=? AND COALESCE(system_kind,'')!='TRASH'",
                (self.workspace_id, folder_id),
            ).fetchone():
                raise NotFoundError("FOLDER_NOT_FOUND")
            row = db.execute(
                "SELECT * FROM home_conversations WHERE workspace_id=? AND conversation_id=?",
                (self.workspace_id, conversation_id),
            ).fetchone()
            now = _now()
            validated_message["timestamp"] = now
            if row:
                if row["deleted_at"] is not None:
                    raise ConflictError("CONVERSATION_TRASHED")
                if expected_version is None or row["version"] != expected_version:
                    raise ConflictError("VERSION_CONFLICT")
                version = expected_version + 1
                db.execute(
                    """UPDATE home_conversations SET folder_id=?,title=?,title_is_custom=?,version=?,updated_at=?
                       WHERE workspace_id=? AND conversation_id=?""",
                    (folder_id, title, int(conversation["title_is_custom"]), version, now, self.workspace_id, conversation_id),
                )
                profile_snapshot = row["business_profile_id"]
            else:
                if expected_version is not None:
                    raise ConflictError("VERSION_CONFLICT")
                version = 1
                profile_snapshot = business_profile_id
                db.execute(
                    "INSERT INTO home_conversations VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        self.workspace_id, conversation_id, folder_id, profile_snapshot, title,
                        int(conversation["title_is_custom"]), version, now, now, None, None,
                    ),
                )
            self._append_message(db, conversation_id, validated_message)
            turn_id = str(uuid.uuid4())
            model_request_id = str(uuid.uuid4())
            self._event(
                db, conversation_id, turn_id, model_request_id, "USER_TURN_ACCEPTED",
                request, actor, session, {"message_id": validated_message["id"]}, outcome="ACCEPTED",
            )
            self._event(
                db, conversation_id, turn_id, model_request_id, "MODEL_REQUEST_PENDING",
                request, actor, session, {"message_id": validated_message["id"]}, outcome="PENDING",
            )
            return {
                "schema_version": API_SCHEMA_VERSION,
                "turn_id": turn_id,
                "model_request_id": model_request_id,
                "conversation_id": conversation_id,
                "conversation_version": version,
                "user_message_digest": hashlib.sha256(validated_message["content"].encode()).hexdigest(),
                "accepted_at": now,
            }

        return self._command(
            "accept_user_turn", idempotency_key, actor,
            {"method": "POST", "canonical_path": f"/v1/home/conversations/{conversation_id}/turns/user", "normalized_body": normalized_body, "precondition_etag": expected_version},
            mutate,
        )

    def _pending_event(self, db: sqlite3.Connection, conversation_id: str, model_request_id: str) -> sqlite3.Row:
        row = db.execute(
            """SELECT * FROM home_events WHERE workspace_id=? AND conversation_id=? AND model_request_id=?
               AND event_type='MODEL_REQUEST_PENDING'""",
            (self.workspace_id, conversation_id, model_request_id),
        ).fetchone()
        if not row:
            raise NotFoundError("MODEL_REQUEST_NOT_FOUND")
        return row

    def _ensure_no_terminal(self, db: sqlite3.Connection, model_request_id: str) -> None:
        if db.execute(
            "SELECT 1 FROM home_events WHERE model_request_id=? AND event_type IN ('MODEL_COMPLETED','MODEL_FAILED','MODEL_CANCELLED','MODEL_TIMED_OUT')",
            (model_request_id,),
        ).fetchone():
            raise ConflictError("TERMINAL_ALREADY_COMMITTED")

    def append_assistant_turn(
        self, conversation_id: str, message: dict[str, Any], expected_version: int, *,
        turn_id: str, model_request_id: str, request_id: str, idempotency_key: str,
        actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        conversation = _validate_safe_id(conversation_id, "INVALID_CONVERSATION_ID")
        turn = _validate_uuid(turn_id, "INVALID_TURN_ID")
        model_request = _validate_uuid(model_request_id, "INVALID_MODEL_REQUEST_ID")
        request = _validate_uuid(request_id, "INVALID_REQUEST_ID")
        validated = self._validate_message(message, authoritative_timestamp=True)
        if validated["role"] != "butler":
            raise ValidationError("BUTLER_TURN_ROLE_REQUIRED")
        session = self._session_digest(actor, session_digest)

        def mutate(db: sqlite3.Connection) -> dict[str, Any]:
            pending = self._pending_event(db, conversation, model_request)
            if pending["turn_id"] != turn:
                raise ConflictError("TURN_CORRELATION_MISMATCH")
            self._ensure_no_terminal(db, model_request)
            row = db.execute(
                "SELECT version FROM home_conversations WHERE workspace_id=? AND conversation_id=? AND deleted_at IS NULL",
                (self.workspace_id, conversation),
            ).fetchone()
            if not row:
                raise NotFoundError("CONVERSATION_NOT_FOUND")
            if row["version"] != expected_version:
                raise ConflictError("VERSION_CONFLICT")
            now = _now()
            validated["timestamp"] = now
            self._append_message(db, conversation, validated)
            version = expected_version + 1
            db.execute(
                "UPDATE home_conversations SET version=?,updated_at=? WHERE workspace_id=? AND conversation_id=?",
                (version, now, self.workspace_id, conversation),
            )
            self._event(
                db, conversation, turn, model_request, "MODEL_COMPLETED", request,
                actor, session, {"message_id": validated["id"]}, outcome="COMPLETED",
            )
            return {
                "schema_version": API_SCHEMA_VERSION, "turn_id": turn,
                "model_request_id": model_request, "terminal_type": "COMPLETED",
                "terminal_count": 1, "assistant_message_count": 1,
                "committed_at": now, "error_code": None,
            }

        return self._command(
            "complete_model_request", idempotency_key, actor,
            {"method": "POST", "canonical_path": f"/v1/home/model-requests/{model_request}/terminal", "normalized_body": {"state": "COMPLETED", "turn_id": turn, "message": {**validated, "timestamp": "SERVER_AUTHORITATIVE"}}, "precondition_etag": expected_version},
            mutate,
        )

    def record_terminal(
        self, conversation_id: str, state: Literal["FAILED", "CANCELLED", "TIMED_OUT"],
        error_code: str, *, turn_id: str, model_request_id: str, request_id: str,
        idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        conversation = _validate_safe_id(conversation_id, "INVALID_CONVERSATION_ID")
        if state not in {"FAILED", "CANCELLED", "TIMED_OUT"}:
            raise ValidationError("INVALID_TERMINAL_STATE")
        if not isinstance(error_code, str) or not _ERROR_CODE.fullmatch(error_code):
            raise ValidationError("INVALID_ERROR_CODE")
        turn = _validate_uuid(turn_id, "INVALID_TURN_ID")
        model_request = _validate_uuid(model_request_id, "INVALID_MODEL_REQUEST_ID")
        request = _validate_uuid(request_id, "INVALID_REQUEST_ID")
        session = self._session_digest(actor, session_digest)

        def mutate(db: sqlite3.Connection) -> dict[str, Any]:
            pending = self._pending_event(db, conversation, model_request)
            if pending["turn_id"] != turn:
                raise ConflictError("TURN_CORRELATION_MISMATCH")
            self._ensure_no_terminal(db, model_request)
            committed = _now()
            self._event(
                db, conversation, turn, model_request, f"MODEL_{state}", request,
                actor, session, {}, outcome=state, error_code=error_code,
            )
            return {
                "schema_version": API_SCHEMA_VERSION, "turn_id": turn,
                "model_request_id": model_request, "terminal_type": state,
                "terminal_count": 1, "assistant_message_count": 0,
                "committed_at": committed, "error_code": error_code,
            }

        return self._command(
            "terminate_model_request", idempotency_key, actor,
            {"method": "POST", "canonical_path": f"/v1/home/model-requests/{model_request}/terminal", "normalized_body": {"state": state, "turn_id": turn, "error_code": error_code}, "precondition_etag": None},
            mutate,
        )

    def reconcile_interrupted_requests(self) -> dict[str, int]:
        if self.read_only:
            return {"pending": 0, "reconciled": 0}
        db = self._connect(read_only=True)
        try:
            rows = list(db.execute(
                """SELECT p.conversation_id,p.turn_id,p.model_request_id FROM home_events p
                   WHERE p.workspace_id=? AND p.event_type='MODEL_REQUEST_PENDING'
                   AND p.model_request_id IS NOT NULL AND NOT EXISTS(
                     SELECT 1 FROM home_events t WHERE t.model_request_id=p.model_request_id
                     AND t.event_type IN ('MODEL_COMPLETED','MODEL_FAILED','MODEL_CANCELLED','MODEL_TIMED_OUT'))""",
                (self.workspace_id,),
            ))
        finally:
            db.close()
        reconciled = 0
        for row in rows:
            key = str(uuid.uuid5(uuid.NAMESPACE_URL, f"butler-interrupted:{row['model_request_id']}"))
            request = str(uuid.uuid5(uuid.NAMESPACE_URL, f"butler-interrupted-request:{row['model_request_id']}"))
            try:
                self.record_terminal(
                    row["conversation_id"], "FAILED", "PROCESS_RESTART_INTERRUPTED",
                    turn_id=row["turn_id"], model_request_id=row["model_request_id"],
                    request_id=request, idempotency_key=key, actor="system-reconciler",
                )
                reconciled += 1
            except ConflictError:
                continue
        return {"pending": len(rows), "reconciled": reconciled}

    def _conversation_mutation(
        self, operation: str, conversation_id: str, expected_version: int,
        normalized_body: dict[str, Any], request_id: str, idempotency_key: str,
        actor: str, session_digest: str | None,
        mutate: Callable[[sqlite3.Connection, sqlite3.Row, str, int, str], dict[str, Any]],
        *, require_trashed: bool = False,
    ) -> dict[str, Any]:
        conversation = _validate_safe_id(conversation_id, "INVALID_CONVERSATION_ID")
        if isinstance(expected_version, bool) or expected_version < 1:
            raise ValidationError("INVALID_VERSION")
        request = _validate_uuid(request_id, "INVALID_REQUEST_ID")
        session = self._session_digest(actor, session_digest)

        def handler(db: sqlite3.Connection) -> dict[str, Any]:
            row = db.execute(
                "SELECT * FROM home_conversations WHERE workspace_id=? AND conversation_id=?",
                (self.workspace_id, conversation),
            ).fetchone()
            if not row or (require_trashed and row["deleted_at"] is None) or (not require_trashed and row["deleted_at"] is not None):
                raise NotFoundError("TRASHED_CONVERSATION_NOT_FOUND" if require_trashed else "CONVERSATION_NOT_FOUND")
            if row["version"] != expected_version:
                raise ConflictError("VERSION_CONFLICT")
            now, version = _now(), expected_version + 1
            return mutate(db, row, now, version, session)

        return self._command(
            operation, idempotency_key, actor,
            {"method": "COMMAND", "canonical_path": f"/v1/home/conversations/{conversation}/{operation}", "normalized_body": normalized_body, "precondition_etag": expected_version},
            handler,
        )

    def move(
        self, conversation_id: str, folder_id: str, expected_version: int, *,
        request_id: str, idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        folder = _validate_safe_id(folder_id, "INVALID_FOLDER_ID")

        def mutate(db: sqlite3.Connection, row: sqlite3.Row, now: str, version: int, session: str) -> dict[str, Any]:
            if not db.execute(
                "SELECT 1 FROM home_folders WHERE workspace_id=? AND folder_id=? AND COALESCE(system_kind,'')!='TRASH'",
                (self.workspace_id, folder),
            ).fetchone():
                raise NotFoundError("FOLDER_NOT_FOUND")
            db.execute(
                "UPDATE home_conversations SET folder_id=?,version=?,updated_at=? WHERE workspace_id=? AND conversation_id=?",
                (folder, version, now, self.workspace_id, conversation_id),
            )
            self._audit(db, "conversation", conversation_id, "MOVE", {"folder_id": row["folder_id"]}, {"folder_id": folder}, request_id, actor, session)
            return {"version": version, "folder_id": folder, "updated_at": now}

        return self._conversation_mutation("move_conversation", conversation_id, expected_version, {"folder_id": folder}, request_id, idempotency_key, actor, session_digest, mutate)

    def rename_conversation(
        self, conversation_id: str, title: str, expected_version: int, *,
        request_id: str, idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        display, _ = _normalize_label(title)

        def mutate(db: sqlite3.Connection, row: sqlite3.Row, now: str, version: int, session: str) -> dict[str, Any]:
            db.execute(
                "UPDATE home_conversations SET title=?,title_is_custom=1,version=?,updated_at=? WHERE workspace_id=? AND conversation_id=?",
                (display, version, now, self.workspace_id, conversation_id),
            )
            self._audit(db, "conversation", conversation_id, "RENAME", {"title": row["title"]}, {"title": display}, request_id, actor, session)
            return {"title": display, "title_is_custom": True, "version": version, "updated_at": now}

        return self._conversation_mutation("rename_conversation", conversation_id, expected_version, {"title": display}, request_id, idempotency_key, actor, session_digest, mutate)

    def trash(
        self, conversation_id: str, expected_version: int, *, request_id: str,
        idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        def mutate(db: sqlite3.Connection, row: sqlite3.Row, now: str, version: int, session: str) -> dict[str, Any]:
            db.execute(
                "UPDATE home_conversations SET folder_id='system-trash',version=?,updated_at=?,deleted_at=? WHERE workspace_id=? AND conversation_id=?",
                (version, now, now, self.workspace_id, conversation_id),
            )
            self._audit(db, "conversation", conversation_id, "TRASH", {"folder_id": row["folder_id"]}, {"folder_id": "system-trash"}, request_id, actor, session)
            return {"deleted": True, "version": version, "deleted_at": now}

        return self._conversation_mutation("trash_conversation", conversation_id, expected_version, {}, request_id, idempotency_key, actor, session_digest, mutate)

    def restore(
        self, conversation_id: str, folder_id: str, expected_version: int, *,
        request_id: str, idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        folder = _validate_safe_id(folder_id, "INVALID_FOLDER_ID")

        def mutate(db: sqlite3.Connection, _row: sqlite3.Row, now: str, version: int, session: str) -> dict[str, Any]:
            if folder == "system-trash" or not db.execute(
                "SELECT 1 FROM home_folders WHERE workspace_id=? AND folder_id=?",
                (self.workspace_id, folder),
            ).fetchone():
                raise NotFoundError("FOLDER_NOT_FOUND")
            db.execute(
                "UPDATE home_conversations SET folder_id=?,version=?,updated_at=?,deleted_at=NULL WHERE workspace_id=? AND conversation_id=?",
                (folder, version, now, self.workspace_id, conversation_id),
            )
            self._audit(db, "conversation", conversation_id, "RESTORE", {"folder_id": "system-trash"}, {"folder_id": folder}, request_id, actor, session)
            return {"restored": True, "folder_id": folder, "version": version, "updated_at": now, "deleted_at": None}

        return self._conversation_mutation("restore_conversation", conversation_id, expected_version, {"folder_id": folder}, request_id, idempotency_key, actor, session_digest, mutate, require_trashed=True)

    def purge(
        self, conversation_id: str, expected_version: int, *, request_id: str,
        idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        def mutate(db: sqlite3.Connection, row: sqlite3.Row, _now_value: str, _version: int, session: str) -> dict[str, Any]:
            count = int(db.execute(
                "SELECT COUNT(*) FROM home_messages WHERE workspace_id=? AND conversation_id=?",
                (self.workspace_id, conversation_id),
            ).fetchone()[0])
            self._audit(db, "conversation", conversation_id, "PERMANENT_DELETE", {"deleted_at": row["deleted_at"], "message_count": count}, None, request_id, actor, session)
            db.execute("DELETE FROM home_conversations WHERE workspace_id=? AND conversation_id=?", (self.workspace_id, conversation_id))
            return {"permanently_deleted": True, "conversation_id": conversation_id}

        return self._conversation_mutation("purge_conversation", conversation_id, expected_version, {"confirmed": True}, request_id, idempotency_key, actor, session_digest, mutate, require_trashed=True)

    def purge_expired_trash(
        self, retention_days: int, *, request_id: str, idempotency_key: str,
        actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or not 1 <= retention_days <= 3650:
            raise ValidationError("INVALID_RETENTION_DAYS")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat(timespec="microseconds").replace("+00:00", "Z")
        session = self._session_digest(actor, session_digest)

        def mutate(db: sqlite3.Connection) -> dict[str, Any]:
            rows = list(db.execute(
                "SELECT * FROM home_conversations WHERE workspace_id=? AND deleted_at IS NOT NULL AND deleted_at<=? ORDER BY deleted_at,conversation_id LIMIT 500",
                (self.workspace_id, cutoff),
            ))
            digests: list[str] = []
            for row in rows:
                conversation = row["conversation_id"]
                self._audit(db, "conversation", conversation, "RETENTION_DELETE", {"deleted_at": row["deleted_at"], "retention_days": retention_days}, None, request_id, actor, session)
                db.execute("DELETE FROM home_conversations WHERE workspace_id=? AND conversation_id=?", (self.workspace_id, conversation))
                digests.append(hashlib.sha256(str(conversation).encode()).hexdigest())
            return {"schema_version": "butler.home.retention-result.v1", "retention_days": retention_days, "cutoff": cutoff, "deleted_count": len(rows), "deleted_id_digests": digests, "bounded_batch": 500}

        return self._command(
            "purge_expired_trash", idempotency_key, actor,
            {"method": "POST", "canonical_path": "/v1/home/trash/purge-expired", "normalized_body": {"retention_days": retention_days}, "precondition_etag": None},
            mutate,
        )

    def reassign_profile(
        self, conversation_id: str, profile_id: str | None, expected_version: int, *,
        request_id: str, idempotency_key: str, actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        if profile_id is not None:
            profile_id = _validate_safe_id(profile_id, "INVALID_PROFILE_ID")

        def mutate(db: sqlite3.Connection, row: sqlite3.Row, now: str, version: int, session: str) -> dict[str, Any]:
            before = row["business_profile_id"]
            db.execute(
                "UPDATE home_conversations SET business_profile_id=?,version=?,updated_at=? WHERE workspace_id=? AND conversation_id=?",
                (profile_id, version, now, self.workspace_id, conversation_id),
            )
            self._audit(db, "conversation", conversation_id, "REASSIGN_PROFILE", {"business_profile_id": before}, {"business_profile_id": profile_id}, request_id, actor, session)
            return {"conversation_id": conversation_id, "business_profile_id": profile_id, "version": version, "updated_at": now}

        return self._conversation_mutation("reassign_profile", conversation_id, expected_version, {"profile_id": profile_id}, request_id, idempotency_key, actor, session_digest, mutate)

    def repair_workspace_mirror(
        self, *, confirmed: bool, request_id: str, idempotency_key: str,
        actor: str, session_digest: str | None = None,
    ) -> dict[str, Any]:
        if not confirmed:
            raise ValidationError("WORKSPACE_MIRROR_REPAIR_CONFIRMATION_REQUIRED")
        if self._startup.status != "READ_ONLY_WORKSPACE_MIRROR_MISSING" or not self.workspace_id or self._key is None:
            raise ConflictError("WORKSPACE_MIRROR_REPAIR_NOT_ALLOWED")
        session = self._session_digest(actor, session_digest)
        key = _validate_uuid(idempotency_key, "INVALID_IDEMPOTENCY_KEY")
        request = _validate_uuid(request_id, "INVALID_REQUEST_ID")
        self._atomic_private_text(self.location.workspace_mirror, self.workspace_id + "\n")
        self._set_status("HOME_READY", count=self._safe_conversation_count())
        try:
            with self._transaction() as db:
                self._audit(db, "workspace", self.workspace_id, "REPAIR_WORKSPACE_MIRROR", None, {"mirror_digest": hashlib.sha256(self.workspace_id.encode()).hexdigest()}, request, actor, session)
                result = {"repaired": True, "startup": self.startup_status()}
                command_id = str(uuid.uuid4())
                created = _now()
                expires = (datetime.now(timezone.utc) + timedelta(days=COMMAND_REPLAY_DAYS)).isoformat(timespec="microseconds").replace("+00:00", "Z")
                body = {**result, "command_receipt": {"schema_version": API_SCHEMA_VERSION, "command_id": command_id, "operation": "repair_workspace_mirror", "idempotency_key": key, "request_digest": _digest({"confirmed": True}), "status": "COMMITTED", "http_status": 200, "response_digest": _digest(result), "created_at": created, "expires_at": expires, "replayed": False}}
                db.execute("INSERT INTO home_commands VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (command_id, self.workspace_id, actor, "repair_workspace_mirror", API_SCHEMA_VERSION, key, _digest({"confirmed": True}), "COMMITTED", 200, "{}", _canonical(body), created, expires))
                return body
        except Exception:
            try:
                self.location.workspace_mirror.unlink()
            except FileNotFoundError:
                pass
            self._set_status("READ_ONLY_WORKSPACE_MIRROR_MISSING", count=self._safe_conversation_count())
            raise

    def integrity_status(self) -> dict[str, Any]:
        result = "unavailable"
        journal = "UNAVAILABLE"
        version = 0
        if self.path.exists():
            db = self._connect(read_only=True)
            try:
                result = str(db.execute("PRAGMA quick_check").fetchone()[0])
                journal = str(db.execute("PRAGMA journal_mode").fetchone()[0]).upper()
                version = int(db.execute("PRAGMA user_version").fetchone()[0])
            finally:
                db.close()
        return {
            "schema_version": "butler.home.integrity.v2",
            "ok": result == "ok",
            "startup": self.startup_status(),
            "database_path_kind": "APP_DATA_ABSOLUTE",
            "directory_mode": oct(_mode(self.location.root)) if self.location.root.exists() else None,
            "database_mode": oct(_mode(self.path)) if self.path.exists() else None,
            "journal_mode": journal,
            "sqlite_version": sqlite3.sqlite_version,
            "user_version": version,
            "encrypted_message_content": True,
            "key_available": self._key is not None,
        }

    def runtime_status(self) -> dict[str, Any]:
        policy: dict[str, Any] = {"status": "UNKNOWN", "source": None, "digest": None}
        measurement: dict[str, Any] = {"status": "NOT_MEASURED", "source": None, "receipt_digest": None, "measured_at": None, "fresh": None}
        policy_path = self.location.runtime_root / "policy_receipt.json"
        measurement_path = self.location.runtime_root / "measurement_receipt.json"
        if policy_path.exists() and policy_path.is_file() and not policy_path.is_symlink():
            try:
                value = json.loads(policy_path.read_text(encoding="utf-8"))
                expected = {"source", "issued_at", "expires_at", "decision"}
                if isinstance(value, dict) and set(value) == expected and value["decision"] in {"ALLOW", "DENY"}:
                    issued = _validate_utc(value["issued_at"], "issued_at")
                    expires = _validate_utc(value["expires_at"], "expires_at")
                    policy = {"status": "KNOWN", "source": _validate_safe_id(value["source"], "INVALID_POLICY_SOURCE"), "digest": _digest(value)}
                    if _parse_time(expires) <= datetime.now(timezone.utc):
                        policy = {"status": "UNKNOWN", "source": None, "digest": None}
            except Exception:
                policy = {"status": "UNAVAILABLE", "source": None, "digest": None}
        if measurement_path.exists() and measurement_path.is_file() and not measurement_path.is_symlink():
            try:
                value = json.loads(measurement_path.read_text(encoding="utf-8"))
                expected = {"source", "measured_at", "result"}
                if isinstance(value, dict) and set(value) == expected and value["result"] in {"PASS", "FAIL"}:
                    measured = _validate_utc(value["measured_at"], "measured_at")
                    age = datetime.now(timezone.utc) - _parse_time(measured)
                    measurement = {"status": value["result"], "source": _validate_safe_id(value["source"], "INVALID_MEASUREMENT_SOURCE"), "receipt_digest": _digest(value), "measured_at": measured, "fresh": age <= timedelta(hours=24)}
            except Exception:
                measurement = {"status": "UNAVAILABLE", "source": None, "receipt_digest": None, "measured_at": None, "fresh": None}
        return {
            "schema_version": API_SCHEMA_VERSION,
            "policy": policy,
            "measurement": measurement,
            "runtime_activation_allowed": False,
            "generated_at": _now(),
        }
