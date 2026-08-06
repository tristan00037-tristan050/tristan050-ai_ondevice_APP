"""Signed XPC parser boundary contracts for untrusted document bytes."""
from __future__ import annotations

import base64
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .contracts import canonical_json, require_digest, require_uuid, sha256_bytes


class ParserIsolationError(RuntimeError):
    pass


class DocumentParserPort(Protocol):
    @property
    def is_production_parser(self) -> bool: ...

    @property
    def policy_sha256(self) -> str: ...

    def parse(self, data: bytes, extension: str) -> str: ...


RECEIPT_KEYS = {
    "schema_version",
    "key_id",
    "run_id",
    "request_id",
    "nonce_digest",
    "service_identity",
    "executable_sha256",
    "entitlements_sha256",
    "sandbox_policy_sha256",
    "input_sha256",
    "output_sha256",
    "network_denials",
    "file_denials",
    "process_denials",
    "started_monotonic_ns",
    "ended_monotonic_ns",
    "peak_memory_bytes",
    "issued_at_epoch_s",
    "expires_at_epoch_s",
    "terminal_status",
    "signature_b64",
}


def verify_parser_receipt(
    receipt: Mapping[str, Any],
    *,
    input_bytes: bytes,
    output_bytes: bytes,
    public_key_bytes: bytes,
    expected_key_id: str,
    expected_run_id: str,
    expected_request_id: str,
    expected_nonce_digest: str,
    expected_service_identity: str,
    expected_executable_sha256: str,
    expected_entitlements_sha256: str,
    expected_sandbox_policy_sha256: str,
    now_epoch_s: int,
) -> None:
    if type(receipt) is not dict or set(receipt) != RECEIPT_KEYS:
        raise ParserIsolationError("PARSER_RECEIPT_INVALID")
    require_uuid(expected_run_id, "PARSER_RUN_INVALID")
    require_uuid(expected_request_id, "PARSER_REQUEST_INVALID")
    for value, code in (
        (expected_key_id, "PARSER_KEY_ID_INVALID"),
        (expected_nonce_digest, "PARSER_NONCE_INVALID"),
        (expected_executable_sha256, "PARSER_EXECUTABLE_INVALID"),
        (expected_entitlements_sha256, "PARSER_ENTITLEMENTS_INVALID"),
        (expected_sandbox_policy_sha256, "PARSER_SANDBOX_POLICY_INVALID"),
    ):
        require_digest(value, code)
    if (
        receipt.get("schema_version") != "butler.helper1.parser-isolation-receipt.v1"
        or receipt.get("key_id") != expected_key_id
        or receipt.get("run_id") != expected_run_id
        or receipt.get("request_id") != expected_request_id
        or receipt.get("nonce_digest") != expected_nonce_digest
        or receipt.get("service_identity") != expected_service_identity
        or receipt.get("executable_sha256") != expected_executable_sha256
        or receipt.get("entitlements_sha256") != expected_entitlements_sha256
        or receipt.get("sandbox_policy_sha256") != expected_sandbox_policy_sha256
        or receipt.get("input_sha256") != sha256_bytes(input_bytes)
        or receipt.get("output_sha256") != sha256_bytes(output_bytes)
        or receipt.get("terminal_status") != "SUCCESS"
    ):
        raise ParserIsolationError("PARSER_RECEIPT_BINDING_INVALID")
    integer_fields = (
        "network_denials",
        "file_denials",
        "process_denials",
        "started_monotonic_ns",
        "ended_monotonic_ns",
        "peak_memory_bytes",
        "issued_at_epoch_s",
        "expires_at_epoch_s",
    )
    if any(type(receipt.get(key)) is not int or receipt[key] < 0 for key in integer_fields):
        raise ParserIsolationError("PARSER_RECEIPT_METRICS_INVALID")
    if receipt["ended_monotonic_ns"] <= receipt["started_monotonic_ns"]:
        raise ParserIsolationError("PARSER_RECEIPT_INTERVAL_INVALID")
    if (
        not receipt["issued_at_epoch_s"] <= now_epoch_s < receipt["expires_at_epoch_s"]
        or receipt["expires_at_epoch_s"] - receipt["issued_at_epoch_s"] > 3600
    ):
        raise ParserIsolationError("PARSER_RECEIPT_TIME_INVALID")
    if (
        not isinstance(public_key_bytes, bytes)
        or len(public_key_bytes) != 32
        or hashlib.sha256(public_key_bytes).hexdigest() != expected_key_id
    ):
        raise ParserIsolationError("PARSER_TRUST_ROOT_INVALID")
    try:
        signature = base64.b64decode(str(receipt.get("signature_b64")), validate=True)
        if len(signature) != 64:
            raise ValueError
        unsigned = {key: value for key, value in receipt.items() if key != "signature_b64"}
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature, canonical_json(unsigned)
        )
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ParserIsolationError("PARSER_RECEIPT_SIGNATURE_INVALID") from exc


@dataclass(frozen=True, slots=True)
class NativeXPCParser:
    """Adapter for a signed native XPC call injected by the composition root."""

    public_key_bytes: bytes
    expected_key_id: str
    service_identity: str
    executable_sha256: str
    entitlements_sha256: str
    sandbox_policy_sha256: str
    xpc_call: Callable[[Mapping[str, Any], bytes], Mapping[str, Any]]
    clock: Callable[[], int] = lambda: int(time.time())

    @property
    def is_production_parser(self) -> bool:
        return True

    @property
    def policy_sha256(self) -> str:
        return sha256_bytes(
            canonical_json(
                {
                    "schema_version": "butler.helper1.parser-policy.v1",
                    "service_identity": self.service_identity,
                    "executable_sha256": self.executable_sha256,
                    "entitlements_sha256": self.entitlements_sha256,
                    "sandbox_policy_sha256": self.sandbox_policy_sha256,
                }
            )
        )

    def parse(self, data: bytes, extension: str) -> str:
        if extension not in {".docx", ".pdf", ".xlsx", ".md", ".txt"}:
            raise ParserIsolationError("DOCUMENT_TYPE_UNSUPPORTED")
        if not isinstance(data, bytes) or not data:
            raise ParserIsolationError("DOCUMENT_SIZE_LIMIT")
        import os
        import uuid

        run_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        nonce_digest = sha256_bytes(os.urandom(32))
        request = {
            "schema_version": "butler.helper1.parser-request.v1",
            "run_id": run_id,
            "request_id": request_id,
            "nonce_digest": nonce_digest,
            "extension": extension,
            "input_sha256": sha256_bytes(data),
            "maximum_output_bytes": 32 * 1024 * 1024,
        }
        response = self.xpc_call(request, data)
        if type(response) is not dict or set(response) != {"text_utf8", "receipt"}:
            raise ParserIsolationError("PARSER_XPC_RESPONSE_INVALID")
        output = response.get("text_utf8")
        if not isinstance(output, bytes) or not output or len(output) > request["maximum_output_bytes"]:
            raise ParserIsolationError("PARSER_OUTPUT_INVALID")
        try:
            text = output.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParserIsolationError("PARSER_OUTPUT_INVALID") from exc
        verify_parser_receipt(
            response.get("receipt"),
            input_bytes=data,
            output_bytes=output,
            public_key_bytes=self.public_key_bytes,
            expected_key_id=self.expected_key_id,
            expected_run_id=run_id,
            expected_request_id=request_id,
            expected_nonce_digest=nonce_digest,
            expected_service_identity=self.service_identity,
            expected_executable_sha256=self.executable_sha256,
            expected_entitlements_sha256=self.entitlements_sha256,
            expected_sandbox_policy_sha256=self.sandbox_policy_sha256,
            now_epoch_s=self.clock(),
        )
        return text
