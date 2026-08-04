from __future__ import annotations

import base64
import hashlib
import time
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from butler_pc_core.helper1.contracts import canonical_json, sha256_bytes
from butler_pc_core.helper1.parser_isolation import (
    ParserIsolationError,
    verify_parser_receipt,
)


def _receipt():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    input_bytes = b"untrusted"
    output_bytes = "검증된 텍스트".encode("utf-8")
    now = int(time.time())
    values = {
        "key_id": hashlib.sha256(public).hexdigest(),
        "run_id": str(uuid.uuid4()),
        "request_id": str(uuid.uuid4()),
        "nonce_digest": "a" * 64,
        "service_identity": "com.butler.helper1.parser",
        "executable_sha256": "b" * 64,
        "entitlements_sha256": "c" * 64,
        "sandbox_policy_sha256": "d" * 64,
    }
    unsigned = {
        "schema_version": "butler.helper1.parser-isolation-receipt.v1",
        **values,
        "input_sha256": sha256_bytes(input_bytes),
        "output_sha256": sha256_bytes(output_bytes),
        "network_denials": 0,
        "file_denials": 0,
        "process_denials": 0,
        "started_monotonic_ns": 10,
        "ended_monotonic_ns": 20,
        "peak_memory_bytes": 1024,
        "issued_at_epoch_s": now - 1,
        "expires_at_epoch_s": now + 60,
        "terminal_status": "SUCCESS",
    }
    receipt = {
        **unsigned,
        "signature_b64": base64.b64encode(private.sign(canonical_json(unsigned))).decode("ascii"),
    }
    return receipt, values, input_bytes, output_bytes, public, now


def _verify(receipt, values, input_bytes, output_bytes, public, now):
    return verify_parser_receipt(
        receipt,
        input_bytes=input_bytes,
        output_bytes=output_bytes,
        public_key_bytes=public,
        expected_key_id=values["key_id"],
        expected_run_id=values["run_id"],
        expected_request_id=values["request_id"],
        expected_nonce_digest=values["nonce_digest"],
        expected_service_identity=values["service_identity"],
        expected_executable_sha256=values["executable_sha256"],
        expected_entitlements_sha256=values["entitlements_sha256"],
        expected_sandbox_policy_sha256=values["sandbox_policy_sha256"],
        now_epoch_s=now,
    )


def test_parser_receipt_binds_exact_input_output_and_native_identity() -> None:
    fixture = _receipt()
    assert _verify(*fixture) is None
    receipt, values, input_bytes, output_bytes, public, now = fixture
    with pytest.raises(ParserIsolationError, match="PARSER_RECEIPT_BINDING_INVALID"):
        _verify(receipt, values, input_bytes, output_bytes + b"x", public, now)


def test_parser_receipt_rejects_forged_denial_count_and_stale_time() -> None:
    receipt, values, input_bytes, output_bytes, public, now = _receipt()
    forged = dict(receipt)
    forged["network_denials"] = 99
    with pytest.raises(ParserIsolationError, match="PARSER_RECEIPT_SIGNATURE_INVALID"):
        _verify(forged, values, input_bytes, output_bytes, public, now)
    with pytest.raises(ParserIsolationError, match="PARSER_RECEIPT_TIME_INVALID"):
        _verify(receipt, values, input_bytes, output_bytes, public, now + 120)
