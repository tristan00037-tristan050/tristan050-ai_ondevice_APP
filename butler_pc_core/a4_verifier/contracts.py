"""Versioned contracts shared by the isolated verifier and native authority."""

from __future__ import annotations

import base64
import re
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from .canonical import jcs_bytes, sha256_hex


PROTOCOL_VERSION = "butler.box5.a4.authority_protocol.v5.3"
CHALLENGE_SCHEMA = "butler.box5.a4.authority_challenge.v5.3"
VERIFY_REQUEST_SCHEMA = "butler.box5.a4.verify_request.v5.3"
OBSERVATION_SCHEMA = "butler.box5.a4.verified_observation.v5.3"
AUTHORITY_RESPONSE_SCHEMA = "butler.box5.a4.authority_response.v5.3"
RECEIPT_SCHEMA = "butler.box5.a4.verification_receipt.v5.3"
RECEIPT_CONTRACT_ID = "BUTLER-BOX5-A4-V5.3-NATIVE-AUTHORITY"
MAX_REQUEST_BYTES = 32 * 1024 * 1024
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 512 * 1024
MAX_CLOCK_SKEW_MS = 2_000

_UUID4 = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def canonical_uuid4(value: object) -> str:
    text = str(value)
    if not _UUID4.fullmatch(text):
        raise ValueError("BLOCK_REQUEST_SCHEMA")
    parsed = uuid.UUID(text)
    if parsed.version != 4 or str(parsed) != text:
        raise ValueError("BLOCK_REQUEST_SCHEMA")
    return text


def sha256_value(value: object) -> str:
    text = str(value)
    if not _SHA256.fullmatch(text):
        raise ValueError("BLOCK_REQUEST_SCHEMA")
    return text


@dataclass(frozen=True, slots=True)
class AuthorityChallenge:
    session_id: str
    request_id: str
    nonce_b64: str
    caller_cdhash: str
    deadline_unix_ms: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AuthorityChallenge":
        required = {
            "schema_version",
            "protocol_version",
            "session_id",
            "request_id",
            "nonce_b64",
            "caller_cdhash",
            "deadline_unix_ms",
        }
        if (
            set(value) != required
            or value.get("schema_version") != CHALLENGE_SCHEMA
            or value.get("protocol_version") != PROTOCOL_VERSION
            or type(value.get("deadline_unix_ms")) is not int
            or not _SHA256.fullmatch(str(value.get("caller_cdhash", "")))
        ):
            raise ValueError("BLOCK_REQUEST_SCHEMA")
        try:
            nonce = base64.b64decode(str(value.get("nonce_b64", "")), validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("BLOCK_REQUEST_SCHEMA") from exc
        if len(nonce) != 32:
            raise ValueError("BLOCK_REQUEST_SCHEMA")
        return cls(
            session_id=canonical_uuid4(value["session_id"]),
            request_id=canonical_uuid4(value["request_id"]),
            nonce_b64=str(value["nonce_b64"]),
            caller_cdhash=str(value["caller_cdhash"]),
            deadline_unix_ms=int(value["deadline_unix_ms"]),
        )

    @property
    def nonce_digest(self) -> str:
        return sha256_hex(base64.b64decode(self.nonce_b64, validate=True))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CHALLENGE_SCHEMA,
            "protocol_version": PROTOCOL_VERSION,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "nonce_b64": self.nonce_b64,
            "caller_cdhash": self.caller_cdhash,
            "deadline_unix_ms": self.deadline_unix_ms,
        }


def request_digest(request: Mapping[str, Any]) -> str:
    return sha256_hex(jcs_bytes(request))
