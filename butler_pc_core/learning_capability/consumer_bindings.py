from __future__ import annotations

import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from butler_pc_core.app_data import product_data_root

from .contracts import CAPABILITY_KEYS, lower_hex_digest, normalize_object_digest


class ConsumerBindingError(RuntimeError):
    pass


class ConsumerBindingStore:
    """Durable digest-only proof written only by real product consumers."""

    MAX_FILE_BYTES = 16_384

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self._lock = threading.RLock()

    @contextmanager
    def _process_lock(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        if os.name == "nt" and os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        deadline = time.monotonic() + 2.0
        acquired = False
        try:
            while not acquired:
                try:
                    if os.name == "nt":  # pragma: no cover - Windows CI
                        import msvcrt

                        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise ConsumerBindingError("BINDING_LOCK_FAILED") from exc
                    time.sleep(0.01)
            yield
        finally:
            if acquired:
                try:
                    if os.name == "nt":  # pragma: no cover - Windows CI
                        import msvcrt

                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
            os.close(descriptor)

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": 1, "bindings": {}}

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            if self.path.stat().st_size > self.MAX_FILE_BYTES:
                raise ConsumerBindingError("BINDING_FILE_TOO_LARGE")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if set(data) != {"schema_version", "bindings"}:
                raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
            if data["schema_version"] != 1 or not isinstance(data["bindings"], dict):
                raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
            for key, value in data["bindings"].items():
                if key not in CAPABILITY_KEYS or set(value) != {
                    "object_digest",
                    "consumer_digest",
                }:
                    raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
                normalize_object_digest(value["object_digest"])
                normalize_object_digest(value["consumer_digest"])
            return data
        except ConsumerBindingError:
            raise
        except Exception as exc:
            raise ConsumerBindingError("BINDING_LOAD_FAILED") from exc

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_name(
            f".{self.path.name}.{secrets.token_hex(8)}.tmp"
        )
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(
                    data,
                    handle,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            try:
                directory = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                if os.name != "nt":
                    raise
        except Exception as exc:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise ConsumerBindingError("BINDING_SAVE_FAILED") from exc

    def record(self, key: str, object_digest: str, consumer_id: str) -> None:
        if key not in CAPABILITY_KEYS:
            raise ConsumerBindingError("BINDING_KEY_INVALID")
        normalized = normalize_object_digest(object_digest)
        with self._lock:
            with self._process_lock():
                data = self._load()
                data["bindings"][key] = {
                    "object_digest": normalized,
                    "consumer_digest": lower_hex_digest({"consumer": consumer_id}),
                }
                self._save(data)

    def is_bound(self, key: str, object_digests: Iterable[str]) -> bool:
        normalized = {normalize_object_digest(value) for value in object_digests}
        with self._lock:
            with self._process_lock():
                data = self._load()
        binding = data["bindings"].get(key)
        return bool(binding and binding["object_digest"] in normalized)

    def revision(self) -> str:
        with self._lock:
            with self._process_lock():
                return lower_hex_digest(self._load())


def default_consumer_binding_store() -> ConsumerBindingStore:
    return ConsumerBindingStore(
        product_data_root(
            "learning-capability",
            legacy_name=".butler_learning_capability",
        )
        / "consumer_bindings.json"
    )
