from __future__ import annotations

import json
import os
import secrets
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .contracts import SAFE_INTEGER_MAX, normalize_object_digest


class GenerationStoreError(RuntimeError):
    pass


class DurableGenerationStore:
    MAX_FILE_BYTES = 4096

    def __init__(self, path: Path, *, lock_timeout_seconds: float = 2.0) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self.lock_timeout_seconds = lock_timeout_seconds

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        if os.name == "nt" and os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        deadline = time.monotonic() + self.lock_timeout_seconds
        acquired = False
        try:
            while not acquired:
                try:
                    if os.name == "nt":  # pragma: no cover - exercised on Windows CI
                        import msvcrt

                        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise GenerationStoreError("GENERATION_LOCK_FAILED") from exc
                    time.sleep(0.01)
            yield
        finally:
            if acquired:
                try:
                    if os.name == "nt":  # pragma: no cover - exercised on Windows CI
                        import msvcrt

                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
            os.close(descriptor)

    def _load(self) -> tuple[int, str] | None:
        if not self.path.exists():
            return None
        try:
            if self.path.stat().st_size > self.MAX_FILE_BYTES:
                raise GenerationStoreError("GENERATION_FILE_TOO_LARGE")
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if set(data) != {
                "schema_version",
                "last_generation",
                "last_snapshot_digest",
            }:
                raise GenerationStoreError("GENERATION_SCHEMA_INVALID")
            generation = data["last_generation"]
            if (
                data["schema_version"] != 1
                or isinstance(generation, bool)
                or not isinstance(generation, int)
                or not 0 <= generation <= SAFE_INTEGER_MAX
            ):
                raise GenerationStoreError("GENERATION_SCHEMA_INVALID")
            digest = normalize_object_digest(data["last_snapshot_digest"])
            return generation, digest
        except GenerationStoreError:
            raise
        except Exception as exc:
            raise GenerationStoreError("GENERATION_LOAD_FAILED") from exc

    def _atomic_save(self, generation: int, digest: str) -> None:
        payload = {
            "schema_version": 1,
            "last_generation": generation,
            "last_snapshot_digest": digest,
        }
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
                    payload,
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
            raise GenerationStoreError("GENERATION_SAVE_FAILED") from exc

    def generation_for(self, snapshot_digest: str) -> int:
        digest = normalize_object_digest(snapshot_digest)
        try:
            with self._locked():
                current = self._load()
                if current is not None and current[1] == digest:
                    return current[0]
                if current is None:
                    generation = 1
                else:
                    if current[0] >= SAFE_INTEGER_MAX:
                        raise GenerationStoreError("GENERATION_OVERFLOW")
                    generation = current[0] + 1
                self._atomic_save(generation, digest)
                return generation
        except GenerationStoreError:
            raise
        except Exception as exc:
            raise GenerationStoreError("GENERATION_UNAVAILABLE") from exc
