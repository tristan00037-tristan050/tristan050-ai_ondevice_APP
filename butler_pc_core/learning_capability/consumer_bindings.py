from __future__ import annotations

import threading
import hashlib
import json
import secrets
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

    def __init__(self, path: Path, *, runtime_instance_id: str | None = None) -> None:
        self.path = path
        self.runtime_instance_id = runtime_instance_id or secrets.token_hex(16)
        if (
            len(self.runtime_instance_id) != 32
            or any(char not in "0123456789abcdef" for char in self.runtime_instance_id)
        ):
            raise ConsumerBindingError("RUNTIME_INSTANCE_ID_INVALID")
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
        return {"schema_version": 2, "bindings": {}}

    def _load(self, session: TrustedStateSession) -> dict[str, Any]:
        try:
            data = session.read_json_optional()
            if data is None:
                return self._empty()
            if set(data) != {"schema_version", "bindings"}:
                raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
            if data["schema_version"] == 1:
                return self._empty()
            if data["schema_version"] != 2 or not isinstance(data["bindings"], dict):
                raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
            for key, value in data["bindings"].items():
                if key not in CAPABILITY_KEYS or set(value) != {
                    "schema_version",
                    "authority_key",
                    "authority_revision",
                    "consumer_id",
                    "observed_at",
                    "runtime_instance_id",
                    "binding_sequence",
                    "binding_digest",
                }:
                    raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
                sequence = value["binding_sequence"]
                if (
                    value["schema_version"] != 2
                    or value["authority_key"] != key
                    or type(value["consumer_id"]) is not str
                    or not 1 <= len(value["consumer_id"]) <= 128
                    or type(value["observed_at"]) is not str
                    or type(value["runtime_instance_id"]) is not str
                    or len(value["runtime_instance_id"]) != 32
                    or any(
                        char not in "0123456789abcdef"
                        for char in value["runtime_instance_id"]
                    )
                    or type(sequence) is not int
                    or not 1 <= sequence <= SAFE_INTEGER_MAX
                ):
                    raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
                normalize_object_digest(value["authority_revision"])
                digest = normalize_object_digest(value["binding_digest"])
                unsigned = {
                    field: field_value
                    for field, field_value in value.items()
                    if field != "binding_digest"
                }
                canonical = json.dumps(
                    unsigned,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                expected = hashlib.sha256(
                    b"butler.learning-binding.v2\x00" + canonical
                ).hexdigest()
                if expected != digest:
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
                    and existing["runtime_instance_id"] == self.runtime_instance_id
                ):
                    return
                previous_sequence = (
                    existing["binding_sequence"]
                    if existing and existing["schema_version"] == 2
                    else 0
                )
                if previous_sequence >= SAFE_INTEGER_MAX:
                    raise ConsumerBindingError("BINDING_GENERATION_OVERFLOW")
                record = {
                    "schema_version": 2,
                    "authority_key": key,
                    "authority_revision": normalized,
                    "consumer_id": consumer_id,
                    "runtime_instance_id": self.runtime_instance_id,
                    "observed_at": datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "binding_sequence": previous_sequence + 1,
                }
                canonical = json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                record["binding_digest"] = hashlib.sha256(
                    b"butler.learning-binding.v2\x00" + canonical
                ).hexdigest()
                data["bindings"][key] = record
                self._save(session, data)

    def is_bound(self, key: str, object_digests: Iterable[str]) -> bool:
        normalized = {normalize_object_digest(value) for value in object_digests}
        with self._lock:
            with self._process_lock() as session:
                data = self._load(session)
        binding = data["bindings"].get(key)
        return bool(
            binding
            and binding["authority_revision"] in normalized
            and binding["runtime_instance_id"] == self.runtime_instance_id
        )

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
            bool(
                binding
                and binding["authority_revision"] in normalized
                and binding["runtime_instance_id"] == self.runtime_instance_id
            ),
            lower_hex_digest(data),
        )

    def revision(self) -> str:
        with self._lock:
            with self._process_lock() as session:
                return lower_hex_digest(self._load(session))


_RUNTIME_INSTANCE_ID = secrets.token_hex(16)


def default_consumer_binding_store() -> ConsumerBindingStore:
    return ConsumerBindingStore(
        product_data_root(
            "learning-capability",
            legacy_name=".butler_learning_capability",
        )
        / "consumer_bindings.json",
        runtime_instance_id=_RUNTIME_INSTANCE_ID,
    )
