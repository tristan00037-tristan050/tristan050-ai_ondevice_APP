from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from butler_pc_core.app_data import product_data_root

from .contracts import (
    CAPABILITY_KEYS,
    SAFE_INTEGER_MAX,
    lower_hex_digest,
    normalize_object_digest,
)
from butler_pc_core.strict_json import (
    StrictJsonError,
    dump_canonical_bytes,
    load_strict_bytes,
)
from .trusted_state import PosixTrustedStateFile, TrustedStateError


class ConsumerBindingError(RuntimeError):
    pass


_CONSUMER_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,95}$")


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


class ConsumerBindingStore:
    """Durable digest-only proof written only by real product consumers."""

    MAX_FILE_BYTES = 16_384

    def __init__(self, path: Path) -> None:
        try:
            self._state = PosixTrustedStateFile(
                path,
                maximum_bytes=self.MAX_FILE_BYTES,
                lock_timeout_seconds=2.0,
            )
        except TrustedStateError as exc:
            raise ConsumerBindingError(str(exc)) from exc
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"schema_version": 1, "bindings": {}}

    @classmethod
    def _decode(cls, payload: bytes) -> dict[str, Any]:
        try:
            data = load_strict_bytes(payload, max_bytes=cls.MAX_FILE_BYTES)
            if set(data) != {"schema_version", "bindings"}:
                raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
            if data["schema_version"] != 1 or type(data["bindings"]) is not dict:
                raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
            for key, value in data["bindings"].items():
                if key not in CAPABILITY_KEYS or type(value) is not dict:
                    raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
                if set(value) != {
                    "schema_version",
                    "authority_key",
                    "authority_revision",
                    "consumer_id",
                    "observed_at",
                    "generation",
                    "binding_digest",
                }:
                    raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
                if (
                    value["schema_version"] != 1
                    or value["authority_key"] != key
                    or _CONSUMER_ID.fullmatch(value["consumer_id"]) is None
                    or type(value["generation"]) is not int
                    or not 1 <= value["generation"] <= SAFE_INTEGER_MAX
                    or not isinstance(value["observed_at"], str)
                    or not value["observed_at"].endswith("Z")
                ):
                    raise ConsumerBindingError("BINDING_SCHEMA_INVALID")
                normalize_object_digest(value["authority_revision"])
                expected = lower_hex_digest(
                    {name: item for name, item in value.items() if name != "binding_digest"}
                )
                if normalize_object_digest(value["binding_digest"]) != expected:
                    raise ConsumerBindingError("BINDING_DIGEST_MISMATCH")
            return data
        except ConsumerBindingError:
            raise
        except (StrictJsonError, TypeError, ValueError) as exc:
            raise ConsumerBindingError("BINDING_SCHEMA_INVALID") from exc

    def _read(self, root_descriptor: int) -> dict[str, Any]:
        payload = self._state.read(root_descriptor)
        return self._empty() if payload is None else self._decode(payload)

    def record(self, key: str, object_digest: str, consumer_id: str) -> None:
        if key not in CAPABILITY_KEYS:
            raise ConsumerBindingError("BINDING_KEY_INVALID")
        if not isinstance(consumer_id, str) or _CONSUMER_ID.fullmatch(consumer_id) is None:
            raise ConsumerBindingError("BINDING_CONSUMER_INVALID")
        normalized = normalize_object_digest(object_digest)
        try:
            with self._lock:
                with self._state.locked_root() as root_descriptor:
                    data = self._read(root_descriptor)
                    previous = data["bindings"].get(key)
                    previous_generation = 0 if previous is None else previous["generation"]
                    if previous_generation >= SAFE_INTEGER_MAX:
                        raise ConsumerBindingError("BINDING_GENERATION_OVERFLOW")
                    record = {
                        "schema_version": 1,
                        "authority_key": key,
                        "authority_revision": normalized,
                        "consumer_id": consumer_id,
                        "observed_at": _now(),
                        "generation": previous_generation + 1,
                    }
                    record["binding_digest"] = lower_hex_digest(record)
                    data["bindings"][key] = record
                    payload = dump_canonical_bytes(data)
                    self._decode(payload)
                    self._state.replace(root_descriptor, payload)
                    final = self._state.read(root_descriptor)
                    if final is None or self._decode(final) != data:
                        raise ConsumerBindingError("BINDING_FINAL_VERIFY_FAILED")
        except ConsumerBindingError:
            raise
        except (TrustedStateError, StrictJsonError, TypeError, ValueError) as exc:
            raise ConsumerBindingError("BINDING_SAVE_FAILED") from exc

    def is_bound(self, key: str, object_digests: Iterable[str]) -> bool:
        normalized = {normalize_object_digest(value) for value in object_digests}
        try:
            with self._lock:
                with self._state.locked_root() as root_descriptor:
                    binding = self._read(root_descriptor)["bindings"].get(key)
            return bool(binding and binding["authority_revision"] in normalized)
        except ConsumerBindingError:
            raise
        except (TrustedStateError, StrictJsonError, TypeError, ValueError) as exc:
            raise ConsumerBindingError("BINDING_LOAD_FAILED") from exc

    def revision(self) -> str:
        try:
            with self._lock:
                with self._state.locked_root() as root_descriptor:
                    return lower_hex_digest(self._read(root_descriptor))
        except (TrustedStateError, StrictJsonError, TypeError, ValueError) as exc:
            raise ConsumerBindingError("BINDING_LOAD_FAILED") from exc


def default_consumer_binding_store() -> ConsumerBindingStore:
    return ConsumerBindingStore(
        product_data_root(
            "learning-capability",
            legacy_name=".butler_learning_capability",
        )
        / "consumer_bindings.json"
    )
