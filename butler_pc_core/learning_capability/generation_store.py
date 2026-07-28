from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .contracts import SAFE_INTEGER_MAX, normalize_object_digest
from butler_pc_core.strict_json import (
    StrictJsonError,
    dump_canonical_bytes,
    load_strict_bytes,
)
from .trusted_state import PosixTrustedStateFile, TrustedStateError


class GenerationStoreError(RuntimeError):
    pass


class DurableGenerationStore:
    MAX_FILE_BYTES = 4096

    def __init__(self, path: Path, *, lock_timeout_seconds: float = 2.0) -> None:
        try:
            self._state = PosixTrustedStateFile(
                path,
                maximum_bytes=self.MAX_FILE_BYTES,
                lock_timeout_seconds=lock_timeout_seconds,
            )
        except TrustedStateError as exc:
            raise GenerationStoreError(str(exc)) from exc
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    @contextmanager
    def _locked(self) -> Iterator[int]:
        with self._state.locked_root() as root_descriptor:
            yield root_descriptor

    @staticmethod
    def _decode(payload: bytes) -> tuple[int, str]:
        try:
            data = load_strict_bytes(payload, max_bytes=DurableGenerationStore.MAX_FILE_BYTES)
            if set(data) != {
                "schema_version",
                "last_generation",
                "last_snapshot_digest",
            }:
                raise GenerationStoreError("GENERATION_SCHEMA_INVALID")
            generation = data["last_generation"]
            if (
                data["schema_version"] != 1
                or type(generation) is not int
                or not 0 <= generation <= SAFE_INTEGER_MAX
            ):
                raise GenerationStoreError("GENERATION_SCHEMA_INVALID")
            return generation, normalize_object_digest(data["last_snapshot_digest"])
        except GenerationStoreError:
            raise
        except (StrictJsonError, TypeError, ValueError) as exc:
            raise GenerationStoreError("GENERATION_SCHEMA_INVALID") from exc

    def generation_for(self, snapshot_digest: str) -> int:
        try:
            digest = normalize_object_digest(snapshot_digest)
            with self._locked() as root_descriptor:
                raw = self._state.read(root_descriptor)
                current = None if raw is None else self._decode(raw)
                if current is not None and current[1] == digest:
                    return current[0]
                if current is None:
                    generation = 1
                else:
                    if current[0] >= SAFE_INTEGER_MAX:
                        raise GenerationStoreError("GENERATION_OVERFLOW")
                    generation = current[0] + 1
                payload = dump_canonical_bytes(
                    {
                        "schema_version": 1,
                        "last_generation": generation,
                        "last_snapshot_digest": digest,
                    }
                )
                # Re-parse before persistence so serialization and schema share
                # exactly the same strict decoder used during recovery.
                self._decode(payload)
                self._state.replace(root_descriptor, payload)
                final = self._state.read(root_descriptor)
                if final is None or self._decode(final) != (generation, digest):
                    raise GenerationStoreError("GENERATION_FINAL_VERIFY_FAILED")
                return generation
        except GenerationStoreError:
            raise
        except (TrustedStateError, StrictJsonError, TypeError, ValueError) as exc:
            raise GenerationStoreError("GENERATION_UNAVAILABLE") from exc
