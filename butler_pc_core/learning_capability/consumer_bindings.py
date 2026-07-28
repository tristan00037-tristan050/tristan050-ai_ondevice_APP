from __future__ import annotations

import threading
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from butler_pc_core.app_data import product_data_root

from .contracts import (
    CAPABILITY_KEYS,
    SAFE_INTEGER_MAX,
    lower_hex_digest,
    normalize_object_digest,
)
from .trusted_state import (
    TrustedStateError,
    TrustedStateFile,
    TrustedStateSession,
)


class ConsumerBindingError(RuntimeError):
    pass


class ConsumerBindingStore:
    """Durable digest-only proof written only by real product consumers."""

    MAX_FILE_BYTES = 16_384

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._state = TrustedStateFile(
            path,
            max_file_bytes=self.MAX_FILE_BYTES,
        )

    @contextmanager
    def _process_lock(self) -> Iterator[TrustedStateSession]:
        try:
            with self._state.locked() as session:
                yield session
        except TrustedStateError as exc:
            raise ConsumerBindingError(str(exc)) from exc

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": 1, "bindings": {}}

    def _load(self, session: TrustedStateSession) -> dict[str, Any]:
        try:
            data = session.read_json_optional()
            if data is None:
                return self._empty()
            if set(data) != {"schema_version", "bindings"}:
                raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
            if data["schema_version"] != 1 or not isinstance(data["bindings"], dict):
                raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
            for key, value in data["bindings"].items():
                if key not in CAPABILITY_KEYS or set(value) != {
                    "schema_version",
                    "authority_key",
                    "authority_revision",
                    "consumer_id",
                    "observed_at",
                    "generation",
                    "binding_digest",
                }:
                    raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
                generation = value["generation"]
                if (
                    value["schema_version"] != 1
                    or value["authority_key"] != key
                    or type(value["consumer_id"]) is not str
                    or not 1 <= len(value["consumer_id"]) <= 128
                    or type(value["observed_at"]) is not str
                    or type(generation) is not int
                    or not 1 <= generation <= SAFE_INTEGER_MAX
                ):
                    raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
                normalize_object_digest(value["authority_revision"])
                digest = normalize_object_digest(value["binding_digest"])
                unsigned = {
                    field: field_value
                    for field, field_value in value.items()
                    if field != "binding_digest"
                }
                if lower_hex_digest(unsigned) != digest:
                    raise ConsumerBindingError("BINDING_DIGEST_INVALID")
            return data
        except ConsumerBindingError:
            raise
        except Exception as exc:
            raise ConsumerBindingError("BINDING_LOAD_FAILED") from exc

    def _save(
        self,
        session: TrustedStateSession,
        data: dict[str, Any],
    ) -> None:
        try:
            session.atomic_write_json(data)
        except Exception as exc:
            raise ConsumerBindingError("BINDING_SAVE_FAILED") from exc

    def record(self, key: str, object_digest: str, consumer_id: str) -> None:
        if key not in CAPABILITY_KEYS:
            raise ConsumerBindingError("BINDING_KEY_INVALID")
        normalized = normalize_object_digest(object_digest)
        if (
            type(consumer_id) is not str
            or not 1 <= len(consumer_id) <= 128
            or any(ord(char) < 0x20 for char in consumer_id)
        ):
            raise ConsumerBindingError("BINDING_CONSUMER_INVALID")
        with self._lock:
            with self._process_lock() as session:
                data = self._load(session)
                existing = data["bindings"].get(key)
                if (
                    existing
                    and existing["authority_revision"] == normalized
                    and existing["consumer_id"] == consumer_id
                ):
                    return
                previous_generation = existing["generation"] if existing else 0
                if previous_generation >= SAFE_INTEGER_MAX:
                    raise ConsumerBindingError("BINDING_GENERATION_OVERFLOW")
                record = {
                    "schema_version": 1,
                    "authority_key": key,
                    "authority_revision": normalized,
                    "consumer_id": consumer_id,
                    "observed_at": datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "generation": previous_generation + 1,
                }
                record["binding_digest"] = lower_hex_digest(record)
                data["bindings"][key] = record
                self._save(session, data)

    def is_bound(self, key: str, object_digests: Iterable[str]) -> bool:
        normalized = {normalize_object_digest(value) for value in object_digests}
        with self._lock:
            with self._process_lock() as session:
                data = self._load(session)
        binding = data["bindings"].get(key)
        return bool(binding and binding["authority_revision"] in normalized)

    def snapshot_for(
        self,
        key: str,
        object_digests: Iterable[str],
    ) -> tuple[bool, str]:
        if key not in CAPABILITY_KEYS:
            raise ConsumerBindingError("BINDING_KEY_INVALID")
        normalized = {normalize_object_digest(value) for value in object_digests}
        with self._lock:
            with self._process_lock() as session:
                data = self._load(session)
        binding = data["bindings"].get(key)
        return (
            bool(binding and binding["authority_revision"] in normalized),
            lower_hex_digest(data),
        )

    def revision(self) -> str:
        with self._lock:
            with self._process_lock() as session:
                return lower_hex_digest(self._load(session))


def default_consumer_binding_store() -> ConsumerBindingStore:
    return ConsumerBindingStore(
        product_data_root(
            "learning-capability",
            legacy_name=".butler_learning_capability",
        )
        / "consumer_bindings.json"
    )
