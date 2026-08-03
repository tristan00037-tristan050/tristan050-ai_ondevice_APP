from __future__ import annotations

import base64
import hashlib
import time
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from butler_pc_core.helper1.contracts import canonical_json
from butler_pc_core.helper1.measurement import MeasurementError, verify_egress_observation


def _fixture(*, gap: bool = False, pid: int = 42):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    now = int(time.time())
    values = {
        "run_id": str(uuid.uuid4()),
        "request_id": str(uuid.uuid4()),
        "session_digest": "a" * 64,
        "action": "ask",
        "nonce_digest": "b" * 64,
    }
    raw_value = {
        "schema_version": "butler.helper1.egress-raw.v1",
        **values,
        "started_monotonic_ns": 10,
        "ended_monotonic_ns": 20,
        "root_pid": 42,
        "process_pids": [42],
        "process_closure_complete": True,
        "records": [
            {
                "sequence": 0,
                "pid": pid,
                "kind": "send",
                "protocol": "tcp",
                "destination_class": "external",
                "sent_bytes": 0,
                "gap": gap,
            }
        ],
    }
    raw = canonical_json(raw_value)
    unsigned = {
        "schema_version": "butler.helper1.egress-observation.v1",
        "key_id": hashlib.sha256(public).hexdigest(),
        **values,
        "raw_observation_sha256": hashlib.sha256(raw).hexdigest(),
        "policy_sha256": "c" * 64,
        "record_count": 1,
        "sent_bytes": 0,
        "connection_attempts": 1,
        "gap_count": int(gap),
        "process_closure_complete": True,
        "external_send_zero": False,
        "started_monotonic_ns": 10,
        "ended_monotonic_ns": 20,
        "issued_at_epoch_s": now - 1,
        "expires_at_epoch_s": now + 60,
    }
    receipt = {
        **unsigned,
        "signature_b64": base64.b64encode(private.sign(canonical_json(unsigned))).decode("ascii"),
    }
    return raw, receipt, public, values, now


def _verify(raw, receipt, public, values, now):
    return verify_egress_observation(
        raw,
        receipt,
        public_key_bytes=public,
        expected_key_id=hashlib.sha256(public).hexdigest(),
        expected_run_id=values["run_id"],
        expected_request_id=values["request_id"],
        expected_session_digest=values["session_digest"],
        expected_action=values["action"],
        expected_nonce_digest=values["nonce_digest"],
        expected_policy_sha256="c" * 64,
        now_epoch_s=now,
    )


def test_zero_is_recomputed_and_connection_attempt_is_not_zero_egress() -> None:
    raw, receipt, public, values, now = _fixture()
    observed = _verify(raw, receipt, public, values, now)
    assert observed.connection_attempts == 1
    assert observed.external_send_zero is False


def test_forged_summary_gap_missing_child_and_stale_receipt_are_blocked() -> None:
    raw, receipt, public, values, now = _fixture()
    forged = dict(receipt)
    forged["external_send_zero"] = True
    with pytest.raises(MeasurementError, match="MEASUREMENT_SUMMARY_MISMATCH"):
        _verify(raw, forged, public, values, now)

    raw_gap, receipt_gap, public_gap, values_gap, now_gap = _fixture(gap=True)
    assert _verify(raw_gap, receipt_gap, public_gap, values_gap, now_gap).gap_count == 1

    raw_child, receipt_child, public_child, values_child, now_child = _fixture(pid=99)
    with pytest.raises(MeasurementError, match="MEASUREMENT_RECORD_INVALID"):
        _verify(raw_child, receipt_child, public_child, values_child, now_child)

    with pytest.raises(MeasurementError, match="MEASUREMENT_TIME_INVALID"):
        _verify(raw, receipt, public, values, now + 120)
