"""Run-scoped OS egress observation receipt verification.

This module verifies native observer output.  It intentionally does not offer
a Python socket-hook observer: such a hook cannot prove child-process or
kernel-visible egress absence on macOS and must never satisfy product gates.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import secrets
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .contracts import canonical_json, require_digest, require_uuid


class MeasurementError(RuntimeError):
    pass


RAW_KEYS = {
    "schema_version",
    "run_id",
    "request_id",
    "session_digest",
    "action",
    "nonce_digest",
    "started_monotonic_ns",
    "ended_monotonic_ns",
    "root_pid",
    "process_pids",
    "process_closure_complete",
    "records",
}
RECORD_KEYS = {
    "sequence",
    "pid",
    "kind",
    "protocol",
    "destination_class",
    "sent_bytes",
    "gap",
}
RECEIPT_KEYS = {
    "schema_version",
    "key_id",
    "run_id",
    "request_id",
    "session_digest",
    "action",
    "nonce_digest",
    "raw_observation_sha256",
    "policy_sha256",
    "record_count",
    "sent_bytes",
    "connection_attempts",
    "gap_count",
    "process_closure_complete",
    "external_send_zero",
    "started_monotonic_ns",
    "ended_monotonic_ns",
    "issued_at_epoch_s",
    "expires_at_epoch_s",
    "signature_b64",
}


def _strict_json(raw: bytes, code: str) -> dict[str, Any]:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 8 * 1024 * 1024:
        raise MeasurementError(code)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise MeasurementError(code)
            value[key] = item
        return value

    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(MeasurementError(code)),
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise MeasurementError(code) from exc
    if type(value) is not dict:
        raise MeasurementError(code)
    return value


def _integer(value: object, minimum: int, code: str) -> int:
    if type(value) is not int or value < minimum:
        raise MeasurementError(code)
    return value


def _string(value: object, allowed: set[str], code: str) -> str:
    if type(value) is not str or value not in allowed:
        raise MeasurementError(code)
    return value


@dataclass(frozen=True, slots=True)
class VerifiedEgressObservation:
    raw_observation_sha256: str
    record_count: int
    sent_bytes: int
    connection_attempts: int
    gap_count: int
    process_closure_complete: bool
    external_send_zero: bool


@dataclass(frozen=True, slots=True)
class ObservationHandle:
    opaque_handle: str
    run_id: str
    request_id: str
    session_digest: str
    action: str
    nonce_digest: str


@dataclass
class NativeEgressMeasurementAuthority:
    """One-shot adapter for a native, OS-visible process-tree observer."""

    public_key_bytes: bytes
    expected_key_id: str
    policy_sha256: str
    start_native: Callable[[Mapping[str, Any]], str]
    stop_native: Callable[[str], Mapping[str, Any]]
    clock: Callable[[], int] = lambda: int(__import__("time").time())
    is_production_observer: bool = True

    def __post_init__(self) -> None:
        require_digest(self.expected_key_id, "MEASUREMENT_KEY_ID_INVALID")
        require_digest(self.policy_sha256, "MEASUREMENT_POLICY_INVALID")
        if (
            not isinstance(self.public_key_bytes, bytes)
            or len(self.public_key_bytes) != 32
            or hashlib.sha256(self.public_key_bytes).hexdigest() != self.expected_key_id
        ):
            raise MeasurementError("MEASUREMENT_TRUST_ROOT_INVALID")
        self._active: set[str] = set()
        self._lock = threading.Lock()

    def begin(self, *, request_id: str, session_digest: str, action: str) -> ObservationHandle:
        require_uuid(request_id, "MEASUREMENT_REQUEST_INVALID")
        require_digest(session_digest, "MEASUREMENT_SESSION_INVALID")
        if action not in {"ask", "search", "index"}:
            raise MeasurementError("MEASUREMENT_ACTION_INVALID")
        handle = ObservationHandle(
            opaque_handle="",
            run_id=str(uuid.uuid4()),
            request_id=request_id,
            session_digest=session_digest,
            action=action,
            nonce_digest=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        )
        challenge = {
            "schema_version": "butler.helper1.egress-start.v1",
            "run_id": handle.run_id,
            "request_id": handle.request_id,
            "session_digest": handle.session_digest,
            "action": handle.action,
            "nonce_digest": handle.nonce_digest,
            "policy_sha256": self.policy_sha256,
        }
        opaque = self.start_native(challenge)
        if not isinstance(opaque, str) or not opaque or len(opaque) > 512:
            raise MeasurementError("MEASUREMENT_OBSERVER_START_FAILED")
        with self._lock:
            if opaque in self._active:
                raise MeasurementError("MEASUREMENT_HANDLE_REUSED")
            self._active.add(opaque)
        return ObservationHandle(
            opaque_handle=opaque,
            run_id=handle.run_id,
            request_id=handle.request_id,
            session_digest=handle.session_digest,
            action=handle.action,
            nonce_digest=handle.nonce_digest,
        )

    def finish(self, handle: ObservationHandle) -> VerifiedEgressObservation:
        if type(handle) is not ObservationHandle:
            raise MeasurementError("MEASUREMENT_HANDLE_INVALID")
        with self._lock:
            if handle.opaque_handle not in self._active:
                raise MeasurementError("MEASUREMENT_HANDLE_INVALID")
            self._active.remove(handle.opaque_handle)
        value = self.stop_native(handle.opaque_handle)
        if type(value) is not dict or set(value) != {"raw_observation", "receipt"}:
            raise MeasurementError("MEASUREMENT_OBSERVER_OUTPUT_INVALID")
        raw = value.get("raw_observation")
        receipt = value.get("receipt")
        if not isinstance(raw, bytes) or type(receipt) is not dict:
            raise MeasurementError("MEASUREMENT_OBSERVER_OUTPUT_INVALID")
        return verify_egress_observation(
            raw,
            receipt,
            public_key_bytes=self.public_key_bytes,
            expected_key_id=self.expected_key_id,
            expected_run_id=handle.run_id,
            expected_request_id=handle.request_id,
            expected_session_digest=handle.session_digest,
            expected_action=handle.action,
            expected_nonce_digest=handle.nonce_digest,
            expected_policy_sha256=self.policy_sha256,
            now_epoch_s=int(self.clock()),
        )


def verify_egress_observation(
    raw: bytes,
    receipt: Mapping[str, Any],
    *,
    public_key_bytes: bytes,
    expected_key_id: str,
    expected_run_id: str,
    expected_request_id: str,
    expected_session_digest: str,
    expected_action: str,
    expected_nonce_digest: str,
    expected_policy_sha256: str,
    now_epoch_s: int,
) -> VerifiedEgressObservation:
    """Recompute the verdict from raw records and verify its protected signer."""
    require_uuid(expected_run_id, "MEASUREMENT_RUN_INVALID")
    require_uuid(expected_request_id, "MEASUREMENT_REQUEST_INVALID")
    require_digest(expected_session_digest, "MEASUREMENT_SESSION_INVALID")
    require_digest(expected_nonce_digest, "MEASUREMENT_NONCE_INVALID")
    require_digest(expected_policy_sha256, "MEASUREMENT_POLICY_INVALID")
    require_digest(expected_key_id, "MEASUREMENT_KEY_ID_INVALID")
    if expected_action not in {"ask", "search", "index"}:
        raise MeasurementError("MEASUREMENT_ACTION_INVALID")
    if type(receipt) is not dict or set(receipt) != RECEIPT_KEYS:
        raise MeasurementError("MEASUREMENT_RECEIPT_INVALID")
    raw_value = _strict_json(raw, "MEASUREMENT_RAW_INVALID")
    if set(raw_value) != RAW_KEYS:
        raise MeasurementError("MEASUREMENT_RAW_INVALID")
    bindings = {
        "run_id": expected_run_id,
        "request_id": expected_request_id,
        "session_digest": expected_session_digest,
        "action": expected_action,
        "nonce_digest": expected_nonce_digest,
    }
    if (
        raw_value.get("schema_version") != "butler.helper1.egress-raw.v1"
        or receipt.get("schema_version") != "butler.helper1.egress-observation.v1"
        or any(raw_value.get(key) != value for key, value in bindings.items())
        or any(receipt.get(key) != value for key, value in bindings.items())
        or receipt.get("policy_sha256") != expected_policy_sha256
        or receipt.get("key_id") != expected_key_id
    ):
        raise MeasurementError("MEASUREMENT_BINDING_INVALID")
    started = _integer(raw_value.get("started_monotonic_ns"), 0, "MEASUREMENT_INTERVAL_INVALID")
    ended = _integer(raw_value.get("ended_monotonic_ns"), 1, "MEASUREMENT_INTERVAL_INVALID")
    if ended <= started or receipt.get("started_monotonic_ns") != started or receipt.get("ended_monotonic_ns") != ended:
        raise MeasurementError("MEASUREMENT_INTERVAL_INVALID")
    root_pid = _integer(raw_value.get("root_pid"), 1, "MEASUREMENT_PROCESS_CLOSURE_INVALID")
    pids = raw_value.get("process_pids")
    if (
        type(pids) is not list
        or not pids
        or any(type(pid) is not int or pid < 1 for pid in pids)
        or len(set(pids)) != len(pids)
        or root_pid not in pids
        or raw_value.get("process_closure_complete") is not True
    ):
        raise MeasurementError("MEASUREMENT_PROCESS_CLOSURE_INVALID")
    records = raw_value.get("records")
    if type(records) is not list or len(records) > 1_000_000:
        raise MeasurementError("MEASUREMENT_RECORDS_INVALID")
    sent_bytes = attempts = gaps = 0
    for expected_sequence, record in enumerate(records):
        if type(record) is not dict or set(record) != RECORD_KEYS:
            raise MeasurementError("MEASUREMENT_RECORD_INVALID")
        if record.get("sequence") != expected_sequence or record.get("pid") not in pids:
            raise MeasurementError("MEASUREMENT_RECORD_INVALID")
        _string(record.get("kind"), {"connect", "send", "dns", "ipc"}, "MEASUREMENT_RECORD_INVALID")
        _string(record.get("protocol"), {"tcp", "udp", "dns", "unix", "xpc"}, "MEASUREMENT_RECORD_INVALID")
        destination = _string(
            record.get("destination_class"),
            {"external", "loopback", "approved_ipc"},
            "MEASUREMENT_RECORD_INVALID",
        )
        count = _integer(record.get("sent_bytes"), 0, "MEASUREMENT_RECORD_INVALID")
        if type(record.get("gap")) is not bool:
            raise MeasurementError("MEASUREMENT_RECORD_INVALID")
        gaps += int(record["gap"])
        if destination == "external":
            sent_bytes += count
            attempts += int(record["kind"] in {"connect", "send", "dns"})
    raw_digest = hashlib.sha256(raw).hexdigest()
    recomputed = {
        "raw_observation_sha256": raw_digest,
        "record_count": len(records),
        "sent_bytes": sent_bytes,
        "connection_attempts": attempts,
        "gap_count": gaps,
        "process_closure_complete": True,
        "external_send_zero": gaps == 0 and sent_bytes == 0 and attempts == 0,
    }
    if any(receipt.get(key) != value for key, value in recomputed.items()):
        raise MeasurementError("MEASUREMENT_SUMMARY_MISMATCH")
    issued = _integer(receipt.get("issued_at_epoch_s"), 0, "MEASUREMENT_TIME_INVALID")
    expires = _integer(receipt.get("expires_at_epoch_s"), 1, "MEASUREMENT_TIME_INVALID")
    if not issued <= now_epoch_s < expires or expires - issued > 3600:
        raise MeasurementError("MEASUREMENT_TIME_INVALID")
    if not isinstance(public_key_bytes, bytes) or len(public_key_bytes) != 32 or hashlib.sha256(public_key_bytes).hexdigest() != expected_key_id:
        raise MeasurementError("MEASUREMENT_TRUST_ROOT_INVALID")
    signature_b64 = receipt.get("signature_b64")
    try:
        if type(signature_b64) is not str:
            raise ValueError
        signature = base64.b64decode(signature_b64, validate=True)
        if len(signature) != 64:
            raise ValueError
        unsigned = {key: value for key, value in receipt.items() if key != "signature_b64"}
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature, canonical_json(unsigned)
        )
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise MeasurementError("MEASUREMENT_SIGNATURE_INVALID") from exc
    return VerifiedEgressObservation(**recomputed)
