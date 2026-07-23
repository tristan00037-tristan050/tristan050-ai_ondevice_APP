"""Unsigned verified-observation assembly for the isolated A4 verifier."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    OBSERVATION_SCHEMA,
    PROTOCOL_VERSION,
    RECEIPT_CONTRACT_ID,
    RECEIPT_SCHEMA,
    AuthorityChallenge,
)


def bind_verified_receipt(
    receipt: Mapping[str, Any],
    *,
    challenge: AuthorityChallenge,
    request_digest: str,
    source_payload_digest: str,
) -> dict[str, Any]:
    bound = dict(receipt)
    bound.update(
        {
            "schema_version": RECEIPT_SCHEMA,
            "contract_id": RECEIPT_CONTRACT_ID,
            "protocol_version": PROTOCOL_VERSION,
            "authority_session_id": challenge.session_id,
            "authority_request_id": challenge.request_id,
            "authority_nonce_digest": challenge.nonce_digest,
            "caller_cdhash": challenge.caller_cdhash,
            "request_digest": request_digest,
            "source_payload_digest": source_payload_digest,
            "request_deadline_unix_ms": challenge.deadline_unix_ms,
        }
    )
    return bound


def verified_observation(
    receipt: Mapping[str, Any],
    *,
    challenge: AuthorityChallenge,
    request_digest: str,
    source_payload_digest: str,
) -> dict[str, Any]:
    return {
        "schema_version": OBSERVATION_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "status": "PASS",
        "error_code": "NONE",
        "authority_session_id": challenge.session_id,
        "authority_request_id": challenge.request_id,
        "authority_nonce_digest": challenge.nonce_digest,
        "request_digest": request_digest,
        "source_payload_digest": source_payload_digest,
        "receipt": bind_verified_receipt(
            receipt,
            challenge=challenge,
            request_digest=request_digest,
            source_payload_digest=source_payload_digest,
        ),
    }
