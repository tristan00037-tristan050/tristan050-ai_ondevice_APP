"""Public-key-only client for the Box5 A4 native XPC authority.

The product process can request one typed verification operation.  It cannot
select an executable, verifier, trust file, or signing payload and never gains
access to private key material.  The bundled native bridge is located from the
installed package, connects to the fixed XPC service, and returns a receipt
whose domain-separated signature is verified again here.
"""

from __future__ import annotations

import base64
import ctypes
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from butler_pc_core.a4_verifier.canonical import receipt_signing_bytes
from butler_pc_core.a4_verifier.contracts import (
    AUTHORITY_RESPONSE_SCHEMA,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    MAX_SOURCE_BYTES,
    PROTOCOL_VERSION,
    RECEIPT_CONTRACT_ID,
    RECEIPT_SCHEMA,
)
from butler_pc_core.a4_verifier.errors import A4AuthorityError, PUBLIC_ERROR_CODES

from .reconciliation_v2 import (
    A4ContractError,
    jcs_bytes,
    sha256_bytes,
    strict_json_loads,
)


AUTHORITY_TRUST_SCHEMA = "butler.box5.a4.verifier_authority_trust.v5.3"
AUTHORITY_TRANSPORT = "native-xpc-v5.3"
PRODUCER_REQUEST_SCHEMA = "butler.box5.a4.producer_request.v5.3"
_IDENTIFIER = re.compile(r"[A-Za-z0-9._-]{3,80}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UUID4 = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)


@dataclass(frozen=True, slots=True)
class VerifierAuthorityTrust:
    authority_id: str
    signer_key_id: str
    public_key: bytes
    key_epoch: int
    trust_digest: str
    environment: str
    not_before: datetime
    not_after: datetime
    minimum_key_epoch: int
    revoked_key_ids: frozenset[str]
    expected_authority_cdhash: str
    expected_verifier_cdhash: str


def _block(code: A4AuthorityError) -> None:
    raise A4ContractError(code.value)


def verify_authority_receipt_signature(
    receipt: Mapping[str, Any], trust: VerifierAuthorityTrust
) -> dict[str, Any]:
    """Verify the fixed v5.3 receipt and domain-separated Ed25519 signature."""

    verified = dict(receipt)
    signature_text = verified.pop("signature", None)
    if (
        verified.get("schema_version") != RECEIPT_SCHEMA
        or verified.get("contract_id") != RECEIPT_CONTRACT_ID
        or verified.get("protocol_version") != PROTOCOL_VERSION
        or verified.get("authority_id") != trust.authority_id
        or verified.get("signer_key_id") != trust.signer_key_id
        or verified.get("signer_key_epoch") != trust.key_epoch
        or verified.get("signer_trust_digest") != trust.trust_digest
        or verified.get("authority_cdhash") != trust.expected_authority_cdhash
        or verified.get("verifier_cdhash") != trust.expected_verifier_cdhash
        or trust.signer_key_id in trust.revoked_key_ids
        or trust.key_epoch < trust.minimum_key_epoch
        or not isinstance(signature_text, str)
    ):
        _block(A4AuthorityError.SIGNATURE)
    try:
        signature = base64.urlsafe_b64decode(
            signature_text + "=" * (-len(signature_text) % 4)
        )
        if len(signature) != 64:
            raise ValueError
        Ed25519PublicKey.from_public_bytes(trust.public_key).verify(
            signature, receipt_signing_bytes(verified)
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise A4ContractError(A4AuthorityError.SIGNATURE.value) from exc
    return {**verified, "signature": signature_text}


def _read_regular(path: Path, *, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 1
            or before.st_size > maximum
            or before.st_mode & 0o022
        ):
            _block(A4AuthorityError.TRUST_POLICY)
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            len(raw) > maximum
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            _block(A4AuthorityError.TRUST_POLICY)
        return raw
    except A4ContractError:
        raise
    except OSError as exc:
        raise A4ContractError(A4AuthorityError.TRUST_POLICY.value) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _block(A4AuthorityError.TRUST_POLICY)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise A4ContractError(A4AuthorityError.TRUST_POLICY.value) from exc
    return parsed.astimezone(timezone.utc)


def load_authority_trust(
    path: Path,
    *,
    now: datetime,
    allow_test_authority: bool = False,
) -> VerifierAuthorityTrust:
    raw = _read_regular(path, maximum=32_768)
    document = strict_json_loads(raw)
    required = {
        "schema_version",
        "enabled",
        "environment",
        "authority_id",
        "transport",
        "algorithm",
        "signer_key_id",
        "public_key_b64",
        "key_epoch",
        "minimum_key_epoch",
        "revoked_key_ids",
        "not_before_utc",
        "not_after_utc",
        "expected_authority_cdhash",
        "expected_verifier_cdhash",
    }
    if (
        not isinstance(document, dict)
        or set(document) != required
        or raw not in {jcs_bytes(document), jcs_bytes(document) + b"\n"}
        or document.get("schema_version") != AUTHORITY_TRUST_SCHEMA
        or document.get("enabled") is not True
        or document.get("transport") != AUTHORITY_TRANSPORT
        or document.get("algorithm") != "Ed25519"
    ):
        _block(A4AuthorityError.TRUST_POLICY)
    environment = document.get("environment")
    if environment != "PRODUCTION" and not (
        allow_test_authority and environment == "TEST"
    ):
        _block(A4AuthorityError.TRUST_POLICY)
    authority_id = str(document.get("authority_id", ""))
    signer_key_id = str(document.get("signer_key_id", ""))
    key_epoch = document.get("key_epoch")
    minimum_key_epoch = document.get("minimum_key_epoch")
    revoked = document.get("revoked_key_ids")
    expected_authority_cdhash = str(document.get("expected_authority_cdhash", ""))
    expected_verifier_cdhash = str(document.get("expected_verifier_cdhash", ""))
    invalid_cdhashes = {"0" * 64, "f" * 64}
    if (
        not _IDENTIFIER.fullmatch(authority_id)
        or not _IDENTIFIER.fullmatch(signer_key_id)
        or type(key_epoch) is not int
        or type(minimum_key_epoch) is not int
        or key_epoch < minimum_key_epoch
        or minimum_key_epoch < 0
        or not isinstance(revoked, list)
        or len(revoked) != len(set(revoked))
        or any(not _IDENTIFIER.fullmatch(str(item)) for item in revoked)
        or signer_key_id in revoked
    ):
        _block(A4AuthorityError.KEY_EPOCH)
    if (
        not _SHA256.fullmatch(expected_authority_cdhash)
        or not _SHA256.fullmatch(expected_verifier_cdhash)
        or expected_authority_cdhash in invalid_cdhashes
        or expected_verifier_cdhash in invalid_cdhashes
    ):
        _block(A4AuthorityError.TRUST_POLICY)
    try:
        public_key = base64.b64decode(
            str(document.get("public_key_b64", "")), validate=True
        )
    except (ValueError, TypeError) as exc:
        raise A4ContractError(A4AuthorityError.TRUST_POLICY.value) from exc
    if len(public_key) != 32:
        _block(A4AuthorityError.TRUST_POLICY)
    not_before = _utc(document.get("not_before_utc"))
    not_after = _utc(document.get("not_after_utc"))
    observed = now.astimezone(timezone.utc)
    if not not_before <= observed < not_after:
        _block(A4AuthorityError.TRUST_EXPIRED)
    return VerifierAuthorityTrust(
        authority_id=authority_id,
        signer_key_id=signer_key_id,
        public_key=public_key,
        key_epoch=key_epoch,
        trust_digest=sha256_bytes(raw),
        environment=str(environment),
        not_before=not_before,
        not_after=not_after,
        minimum_key_epoch=minimum_key_epoch,
        revoked_key_ids=frozenset(str(item) for item in revoked),
        expected_authority_cdhash=expected_authority_cdhash,
        expected_verifier_cdhash=expected_verifier_cdhash,
    )


def _read_source_descriptor(source_fd: int) -> bytes:
    duplicate = -1
    try:
        duplicate = os.dup(source_fd)
        before = os.fstat(duplicate)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_SOURCE_BYTES:
            _block(A4AuthorityError.SOURCE_FD)
        os.lseek(duplicate, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = MAX_SOURCE_BYTES + 1
        while remaining:
            chunk = os.read(duplicate, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        source = b"".join(chunks)
        after = os.fstat(duplicate)
        if (
            len(source) != before.st_size
            or len(source) > MAX_SOURCE_BYTES
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        ):
            _block(A4AuthorityError.SOURCE_DIGEST)
        return source
    except A4ContractError:
        raise
    except OSError as exc:
        raise A4ContractError(A4AuthorityError.SOURCE_FD.value) from exc
    finally:
        if duplicate >= 0:
            os.close(duplicate)


class _NativeBridge:
    def __init__(self) -> None:
        library_path = (
            Path(__file__).resolve().parents[2]
            / "a4_verifier"
            / "libButlerA4AuthorityBridge.dylib"
        )
        if not library_path.is_file() or library_path.is_symlink():
            _block(A4AuthorityError.AUTHORITY_UNAVAILABLE)
        try:
            self._library = ctypes.CDLL(str(library_path))
            self._verify = self._library.butler_a4_authority_verify
            self._free = self._library.butler_a4_authority_free
        except (OSError, AttributeError) as exc:
            raise A4ContractError(A4AuthorityError.AUTHORITY_UNAVAILABLE.value) from exc
        byte_pointer = ctypes.POINTER(ctypes.c_uint8)
        self._verify.argtypes = [
            byte_pointer,
            ctypes.c_size_t,
            byte_pointer,
            ctypes.c_size_t,
            ctypes.POINTER(byte_pointer),
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self._verify.restype = ctypes.c_int32
        self._free.argtypes = [byte_pointer, ctypes.c_size_t]
        self._free.restype = None

    @staticmethod
    def _buffer(value: bytes) -> tuple[Any, Any]:
        array_type = ctypes.c_uint8 * len(value)
        storage = array_type.from_buffer_copy(value)
        return storage, ctypes.cast(storage, ctypes.POINTER(ctypes.c_uint8))

    def roundtrip(self, request: bytes, source: bytes, timeout_seconds: int) -> bytes:
        del timeout_seconds  # Native bridge enforces its own fixed deadline.
        request_storage, request_pointer = self._buffer(request)
        source_storage, source_pointer = self._buffer(source)
        output = ctypes.POINTER(ctypes.c_uint8)()
        output_size = ctypes.c_size_t(0)
        status = self._verify(
            request_pointer,
            len(request),
            source_pointer,
            len(source),
            ctypes.byref(output),
            ctypes.byref(output_size),
        )
        _ = (request_storage, source_storage)
        if status != 0 or not output or not 0 < output_size.value <= MAX_RESPONSE_BYTES:
            _block(A4AuthorityError.AUTHORITY_UNAVAILABLE)
        try:
            return ctypes.string_at(output, output_size.value)
        finally:
            self._free(output, output_size.value)


NativeRoundtrip = Callable[[bytes, bytes, int], bytes]


def _native_authority_roundtrip(
    request: bytes, source: bytes, timeout_seconds: int
) -> bytes:
    return _NativeBridge().roundtrip(request, source, timeout_seconds)


def request_authority_verification(
    *,
    authority_trust_path: Path,
    evidence_files: Mapping[str, bytes],
    finance_trust: bytes,
    dictionary: bytes,
    key_material: Mapping[str, str],
    tenant_id: str,
    source_fd: int,
    source_suffix: str,
    now: datetime,
    allow_test_authority: bool = False,
    timeout_seconds: int = 30,
    _roundtrip: NativeRoundtrip | None = None,
) -> dict[str, Any]:
    trust = load_authority_trust(
        authority_trust_path,
        now=now,
        allow_test_authority=allow_test_authority,
    )
    if source_suffix not in {".csv", ".xls", ".xlsx"}:
        _block(A4AuthorityError.REQUEST_SCHEMA)
    source = _read_source_descriptor(source_fd)
    request = {
        "schema_version": PRODUCER_REQUEST_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "tenant_id": tenant_id,
        "source_suffix": source_suffix,
        "source_payload_digest": sha256_bytes(source),
        "authority_trust_digest": trust.trust_digest,
        "evidence_files_b64": {
            name: base64.b64encode(value).decode("ascii")
            for name, value in sorted(evidence_files.items())
        },
        "finance_trust_b64": base64.b64encode(finance_trust).decode("ascii"),
        "dictionary_b64": base64.b64encode(dictionary).decode("ascii"),
        "key_material": dict(key_material),
    }
    payload = jcs_bytes(request)
    if not 0 < len(payload) <= MAX_REQUEST_BYTES:
        _block(A4AuthorityError.REQUEST_SIZE)
    raw_response = (_roundtrip or _native_authority_roundtrip)(
        payload, source, timeout_seconds
    )
    if not 0 < len(raw_response) <= MAX_RESPONSE_BYTES:
        _block(A4AuthorityError.REQUEST_SIZE)
    response = strict_json_loads(raw_response)
    required = {
        "schema_version",
        "protocol_version",
        "status",
        "error_code",
        "authority_session_id",
        "authority_request_id",
        "authority_nonce_digest",
        "request_digest",
        "source_payload_digest",
        "receipt",
    }
    if (
        not isinstance(response, dict)
        or set(response) != required
        or response.get("schema_version") != AUTHORITY_RESPONSE_SCHEMA
        or response.get("protocol_version") != PROTOCOL_VERSION
    ):
        _block(A4AuthorityError.PROTOCOL_VERSION)
    if response.get("status") != "PASS" or response.get("error_code") != "NONE":
        code = str(response.get("error_code", ""))
        raise A4ContractError(
            code if code in PUBLIC_ERROR_CODES else "BLOCK_OFFLINE_VERIFIER"
        )
    receipt = response.get("receipt")
    if (
        not isinstance(receipt, dict)
        or not _UUID4.fullmatch(str(response.get("authority_session_id", "")))
        or not _UUID4.fullmatch(str(response.get("authority_request_id", "")))
        or not _SHA256.fullmatch(str(response.get("authority_nonce_digest", "")))
        or not _SHA256.fullmatch(str(response.get("request_digest", "")))
        or response.get("source_payload_digest") != sha256_bytes(source)
        or receipt.get("authority_session_id") != response["authority_session_id"]
        or receipt.get("authority_request_id") != response["authority_request_id"]
        or receipt.get("authority_nonce_digest") != response["authority_nonce_digest"]
        or receipt.get("request_digest") != response["request_digest"]
        or receipt.get("source_payload_digest") != response["source_payload_digest"]
    ):
        _block(A4AuthorityError.NONCE_BINDING)
    return verify_authority_receipt_signature(receipt, trust)
