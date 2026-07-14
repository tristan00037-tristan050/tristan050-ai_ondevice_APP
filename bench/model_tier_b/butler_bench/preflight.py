from __future__ import annotations

import re
from typing import Any

from .canonical import canonical_sha256
from .errors import ExitCode, FailClass, GateError
from .evidence import verify_receipt

GATE_NAMES = (
    "P0_CODE_CLOSED",
    "ALL_46_DEFECTS_CLOSED",
    "CLEAN_COMMITTED_TREE",
    "GIT_BLOB_MATCH",
    "CI_GREEN",
    "OS_EGRESS_RECEIPT_VALID",
    "PRODUCT_PREFLIGHT_PASS",
    "INDEPENDENT_PREFLIGHT_VERIFY",
    "TRUST_POLICY_CONFIGURED",
    "BASE_FULL_SHA_RESOLVED",
    "BENCHMARK_POLICY_COMPLETE",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PAYLOAD_KEYS = {
    "gate_name", "value", "evidence_subject_sha256", "attestation_sha256",
    "trust_policy_sha256", "source",
}
_APPROVED_SOURCES = {"CI_SIGNED", "TARGET_CONTROLLER_SIGNED", "OWNER_SIGNED", "INDEPENDENT_VERIFIER_SIGNED"}


def validate_m3_gate_receipts(
    receipts: list[dict[str, Any]],
    *,
    expected_subjects: dict[str, str],
) -> dict[str, Any]:
    if set(expected_subjects) != set(GATE_NAMES):
        _block("EXPECTED_GATE_SUBJECT_SET")
    if len(receipts) != len(GATE_NAMES):
        _block("GATE_RECEIPT_CARDINALITY")
    observed: dict[str, str] = {}
    for receipt in receipts:
        digest = verify_receipt(receipt)
        if receipt["receipt_type"] != "preflight_gate":
            _block("GATE_RECEIPT_TYPE")
        payload = receipt["payload"]
        if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
            _block("GATE_PAYLOAD_KEYS")
        gate = payload["gate_name"]
        if gate not in GATE_NAMES or gate in observed:
            _block("GATE_NAME_OR_DUPLICATE")
        if payload["value"] is not True:
            _block("GATE_VALUE_FALSE")
        expected = expected_subjects[gate]
        if not _SHA256.fullmatch(expected) or payload["evidence_subject_sha256"] != expected:
            _block("GATE_SUBJECT_MISMATCH")
        for key in ("attestation_sha256", "trust_policy_sha256"):
            if not isinstance(payload[key], str) or not _SHA256.fullmatch(payload[key]):
                _block("GATE_TRUST_DIGEST")
        if payload["source"] not in _APPROVED_SOURCES:
            _block("GATE_SOURCE_UNTRUSTED")
        if receipt["subject"] != [{"name": gate, "sha256": expected}]:
            _block("GATE_RECEIPT_SUBJECT")
        observed[gate] = digest
    if set(observed) != set(GATE_NAMES):
        _block("GATE_SET")
    payload = {
        "schema_version": "butler.model-tier-b.m3-preflight.v2.8",
        "gate_receipt_sha256": {gate: observed[gate] for gate in GATE_NAMES},
        "m3_start_allowed": True,
        "g1_ready": False,
        "runtime_activation_allowed": 0,
    }
    payload["preflight_subject_sha256"] = canonical_sha256(payload)
    return payload


def validate_m3_start_gates(value: object) -> None:
    """Reject the obsolete caller-supplied all-true JSON contract."""
    if isinstance(value, dict) and "gates" in value:
        _block("CALLER_BOOLEAN_PREFLIGHT_FORBIDDEN")
    _block("SIGNED_GATE_RECEIPTS_REQUIRED")


def _block(detail: str) -> None:
    raise GateError(FailClass.PREFLIGHT, detail, exit_code=ExitCode.PROTOCOL)
