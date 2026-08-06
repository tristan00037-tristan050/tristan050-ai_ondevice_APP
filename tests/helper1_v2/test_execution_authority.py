from __future__ import annotations

import base64
import hashlib
import time
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from butler_pc_core.helper1.contracts import canonical_json
from butler_pc_core.helper1.execution import (
    ExecutionAuthorityError,
    NativeExecutionAuthority,
)


def _signed(private_key: Ed25519PrivateKey, value: dict[str, object]) -> dict[str, object]:
    signature = private_key.sign(canonical_json(value))
    return {**value, "signature_b64": base64.b64encode(signature).decode("ascii")}


def _authority():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = hashlib.sha256(public_key).hexdigest()
    now = int(time.time())
    workspace_id = str(uuid.uuid4())
    generation_id = str(uuid.uuid4())
    grant = _signed(
        private_key,
        {
            "schema_version": "butler.helper1.activation-grant.v3",
            "key_id": key_id,
            "subject_commit": "a" * 40,
            "subject_tree": "b" * 40,
            "workspace_id": workspace_id,
            "generation_id": generation_id,
            "actions": ["ask", "search"],
            "artifact_digests": ["c" * 64],
            "not_before_epoch_s": now - 10,
            "expires_at_epoch_s": now + 600,
            "grant_nonce_sha256": "d" * 64,
        },
    )

    def signer(challenge):
        return _signed(
            private_key,
            {
                **challenge,
                "schema_version": "butler.helper1.execution-receipt.v3",
                "issued_at_epoch_s": now - 1,
                "expires_at_epoch_s": now + 30,
            },
        )

    authority = NativeExecutionAuthority(
        public_key_bytes=public_key,
        expected_public_key_sha256=key_id,
        signed_activation_grant=grant,
        native_signer=signer,
        clock=lambda: now,
    )
    return authority, workspace_id, generation_id


def test_execution_receipt_is_bound_to_request_session_action_and_generation():
    authority, workspace_id, generation_id = _authority()
    request_id = str(uuid.uuid4())
    receipt = authority.issue(
        request_id=request_id,
        session_digest="e" * 64,
        action="ask",
        workspace_id=workspace_id,
        generation_id=generation_id,
        answer_sha256="f" * 64,
    )
    assert receipt.request_id == request_id
    assert receipt.session_digest == "e" * 64
    assert receipt.action == "ask"
    assert receipt.generation_id == generation_id


def test_action_outside_static_grant_is_rejected_before_native_signing():
    authority, workspace_id, generation_id = _authority()
    with pytest.raises(ExecutionAuthorityError, match="EXECUTION_ACTION_NOT_GRANTED"):
        authority.issue(
            request_id=str(uuid.uuid4()),
            session_digest="e" * 64,
            action="display",
            workspace_id=workspace_id,
            generation_id=generation_id,
            answer_sha256="f" * 64,
        )


def test_native_receipt_for_another_request_is_rejected():
    authority, workspace_id, generation_id = _authority()
    original_signer = authority.native_signer
    captured = original_signer(
        {
            "schema_version": "butler.helper1.execution-challenge.v3",
            "key_id": authority.grant.key_id,
            "subject_commit": authority.grant.subject_commit,
            "subject_tree": authority.grant.subject_tree,
            "workspace_id": workspace_id,
            "generation_id": generation_id,
            "request_id": str(uuid.uuid4()),
            "session_digest": "e" * 64,
            "action": "ask",
            "nonce_digest": "1" * 64,
            "answer_sha256": "f" * 64,
        }
    )
    authority.native_signer = lambda _challenge: captured
    with pytest.raises(ExecutionAuthorityError, match="EXECUTION_RECEIPT_BINDING_INVALID"):
        authority.issue(
            request_id=str(uuid.uuid4()),
            session_digest="e" * 64,
            action="ask",
            workspace_id=workspace_id,
            generation_id=generation_id,
            answer_sha256="f" * 64,
        )
