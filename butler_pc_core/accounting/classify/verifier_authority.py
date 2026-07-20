"""Public-only client for the isolated Box5 A4 verifier authority.

The product process sends sealed evidence plus a duplicated source descriptor
to a separately managed local authority.  It never receives a private key or a
generic signing capability.  The authority independently recompiles the raw
source before returning a receipt signed by a build-pinned public key.
"""

from __future__ import annotations

import array
import base64
import os
import re
import socket
import stat
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .reconciliation_v2 import (
    A4ContractError,
    jcs_bytes,
    sha256_bytes,
    strict_json_loads,
)


AUTHORITY_REQUEST_SCHEMA = "butler.box5.a4.authority_request.v1"
AUTHORITY_RESPONSE_SCHEMA = "butler.box5.a4.authority_response.v1"
AUTHORITY_TRUST_SCHEMA = "butler.box5.a4.verifier_authority_trust.v1"
AUTHORITY_TRANSPORT = "unix-scm-rights-v1"
MAX_AUTHORITY_REQUEST_BYTES = 32 * 1024 * 1024
MAX_AUTHORITY_RESPONSE_BYTES = 256 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9._-]{3,80}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class VerifierAuthorityTrust:
    authority_id: str
    signer_key_id: str
    public_key: bytes
    revocation_epoch: int
    trust_digest: str
    environment: str
    not_before: datetime
    not_after: datetime


def verify_authority_receipt_signature(
    receipt: Mapping[str, Any], trust: VerifierAuthorityTrust
) -> dict[str, Any]:
    """Verify an authority receipt without granting any signing capability."""

    verified = dict(receipt)
    signature_text = verified.pop("signature", None)
    if (
        verified.get("authority_id") != trust.authority_id
        or verified.get("signer_key_id") != trust.signer_key_id
        or verified.get("signer_revocation_epoch") != trust.revocation_epoch
        or verified.get("signer_trust_digest") != trust.trust_digest
        or not isinstance(signature_text, str)
    ):
        raise A4ContractError("BLOCK_SIGNATURE")
    try:
        signature = base64.urlsafe_b64decode(
            signature_text + "=" * (-len(signature_text) % 4)
        )
        Ed25519PublicKey.from_public_bytes(trust.public_key).verify(
            signature, jcs_bytes(verified)
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise A4ContractError("BLOCK_SIGNATURE") from exc
    return {**verified, "signature": signature_text}


def _read_regular(path: Path, *, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(path, flags)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size < 1
            or before.st_size > maximum
            or before.st_mode & 0o022
        ):
            raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, maximum + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum:
                raise A4ContractError("BLOCK_RESOURCE_LIMIT")
        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
        return b"".join(chunks)
    except A4ContractError:
        raise
    except OSError as exc:
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE") from exc
    return parsed.astimezone(timezone.utc)


def load_authority_trust(
    path: Path,
    *,
    now: datetime,
    allow_test_authority: bool = False,
) -> VerifierAuthorityTrust:
    raw = _read_regular(path, maximum=16_384)
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
        "revocation_epoch",
        "not_before_utc",
        "not_after_utc",
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
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    environment = document.get("environment")
    if environment != "PRODUCTION" and not (
        allow_test_authority and environment == "TEST"
    ):
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    authority_id = str(document.get("authority_id", ""))
    signer_key_id = str(document.get("signer_key_id", ""))
    epoch = document.get("revocation_epoch")
    if (
        not _IDENTIFIER.fullmatch(authority_id)
        or not _IDENTIFIER.fullmatch(signer_key_id)
        or not isinstance(epoch, int)
        or isinstance(epoch, bool)
        or epoch < 0
    ):
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    try:
        public_key = base64.b64decode(
            str(document.get("public_key_b64", "")), validate=True
        )
    except (ValueError, TypeError) as exc:
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE") from exc
    if len(public_key) != 32:
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    not_before = _utc(document.get("not_before_utc"))
    not_after = _utc(document.get("not_after_utc"))
    observed = now.astimezone(timezone.utc)
    if not not_before <= observed < not_after:
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    return VerifierAuthorityTrust(
        authority_id=authority_id,
        signer_key_id=signer_key_id,
        public_key=public_key,
        revocation_epoch=epoch,
        trust_digest=sha256_bytes(raw),
        environment=str(environment),
        not_before=not_before,
        not_after=not_after,
    )


def _send_request(sock: socket.socket, payload: bytes, source_fd: int) -> None:
    if not 0 < len(payload) <= MAX_AUTHORITY_REQUEST_BYTES:
        raise A4ContractError("BLOCK_RESOURCE_LIMIT")
    descriptor = array.array("i", [source_fd])
    header = struct.pack(">I", len(payload))
    try:
        sent = sock.sendmsg(
            [header],
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, descriptor.tobytes())],
        )
        if sent < len(header):
            sock.sendall(header[sent:])
        sock.sendall(payload)
    except OSError as exc:
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE") from exc


def _read_exact(sock: socket.socket, size: int) -> bytes:
    body = bytearray()
    while len(body) < size:
        try:
            chunk = sock.recv(size - len(body))
        except OSError as exc:
            raise A4ContractError("BLOCK_TRUST_UNAVAILABLE") from exc
        if not chunk:
            raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
        body.extend(chunk)
    return bytes(body)


def _receive_response(sock: socket.socket) -> dict[str, Any]:
    size = struct.unpack(">I", _read_exact(sock, 4))[0]
    if not 0 < size <= MAX_AUTHORITY_RESPONSE_BYTES:
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    response = strict_json_loads(_read_exact(sock, size))
    if not isinstance(response, dict):
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    return response


def request_authority_verification(
    *,
    authority_socket: Path,
    authority_trust_path: Path,
    evidence_files: Mapping[str, bytes],
    finance_trust: bytes,
    dictionary: bytes,
    key_material: Mapping[str, str],
    tenant_id: str,
    source_fd: int,
    source_suffix: str,
    now: datetime,
    request_nonce: str,
    allow_test_authority: bool = False,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    trust = load_authority_trust(
        authority_trust_path,
        now=now,
        allow_test_authority=allow_test_authority,
    )
    try:
        socket_stat = os.lstat(authority_socket)
    except OSError as exc:
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE") from exc
    if (
        not stat.S_ISSOCK(socket_stat.st_mode)
        or socket_stat.st_mode & 0o002
        or socket_stat.st_uid not in {0, os.geteuid()}
    ):
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    request = {
        "schema_version": AUTHORITY_REQUEST_SCHEMA,
        "request_nonce": request_nonce,
        "tenant_id": tenant_id,
        "source_suffix": source_suffix,
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
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout_seconds)
            client.connect(str(authority_socket))
            _send_request(client, payload, source_fd)
            response = _receive_response(client)
    except A4ContractError:
        raise
    except (OSError, TimeoutError) as exc:
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE") from exc
    if (
        set(response)
        != {"schema_version", "request_nonce", "status", "error_code", "receipt"}
        or response.get("schema_version") != AUTHORITY_RESPONSE_SCHEMA
        or response.get("request_nonce") != request_nonce
    ):
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    if response.get("status") != "PASS" or response.get("error_code") != "NONE":
        raise A4ContractError("BLOCK_OFFLINE_VERIFIER")
    if not isinstance(response.get("receipt"), dict):
        raise A4ContractError("BLOCK_TRUST_UNAVAILABLE")
    return verify_authority_receipt_signature(response["receipt"], trust)
