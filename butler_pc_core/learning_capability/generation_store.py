from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .contracts import SAFE_INTEGER_MAX, normalize_object_digest
from .trusted_state import (
    TrustedStateError,
    TrustedStateFile,
    TrustedStateSession,
)


class GenerationStoreError(RuntimeError):
    pass


class DurableGenerationStore:
    MAX_FILE_BYTES = 4096

    def __init__(self, path: Path, *, lock_timeout_seconds: float = 2.0) -> None:
        self.path = path
        self.lock_timeout_seconds = lock_timeout_seconds
        try:
            self._state = TrustedStateFile(
                path,
                max_file_bytes=self.MAX_FILE_BYTES,
                lock_timeout_seconds=lock_timeout_seconds,
            )
        except TrustedStateError as exc:
            raise GenerationStoreError(str(exc)) from exc

    @contextmanager
    def _locked(self) -> Iterator[TrustedStateSession]:
        try:
            with self._state.locked() as session:
                yield session
        except TrustedStateError as exc:
            raise GenerationStoreError(str(exc)) from exc

    def _load(self, session: TrustedStateSession) -> tuple[int, str] | None:
        try:
            data = session.read_json_optional()
            if data is None:
                return None
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

    def _atomic_save(
        self,
        session: TrustedStateSession,
        generation: int,
        digest: str,
    ) -> None:
        payload = {
            "schema_version": 1,
            "last_generation": generation,
            "last_snapshot_digest": digest,
        }
        try:
            session.atomic_write_json(payload)
        except Exception as exc:
            raise GenerationStoreError("GENERATION_SAVE_FAILED") from exc

    def generation_for(self, snapshot_digest: str) -> int:
        digest = normalize_object_digest(snapshot_digest)
        try:
            with self._locked() as session:
                current = self._load(session)
                if current is not None and current[1] == digest:
                    return current[0]
                if current is None:
                    generation = 1
                else:
                    if current[0] >= SAFE_INTEGER_MAX:
                        raise GenerationStoreError("GENERATION_OVERFLOW")
                    generation = current[0] + 1
                self._atomic_save(session, generation, digest)
                return generation
        except GenerationStoreError:
            raise
        except Exception as exc:
            raise GenerationStoreError("GENERATION_UNAVAILABLE") from exc
