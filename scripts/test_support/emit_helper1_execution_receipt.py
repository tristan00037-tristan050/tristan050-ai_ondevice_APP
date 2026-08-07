#!/usr/bin/env python3
"""Emit a deterministic-shape Python Ed25519 receipt for TS interoperability tests."""
from __future__ import annotations

import base64
import hashlib
import json
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REQUEST_ID = "9699ce0c-2597-42ea-a6fa-29cfcb2bb75e"
WORKSPACE_ID = "90321a6a-f937-4d93-b018-d09e8cab4e72"
GENERATION_ID = "3f201e45-366e-48fc-96d7-21c76c399753"
ANSWER = "Python Sidecar가 생성한 검증 대상 답변입니다."


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> None:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    now = int(time.time())
    unsigned = {
        "schema_version": "butler.helper1.execution-receipt.v3",
        "key_id": digest(public_key),
        "subject_commit": "a" * 40,
        "subject_tree": "b" * 40,
        "workspace_id": WORKSPACE_ID,
        "generation_id": GENERATION_ID,
        "request_id": REQUEST_ID,
        "session_digest": "c" * 64,
        "action": "ask",
        "nonce_digest": "f" * 64,
        "answer_sha256": digest(ANSWER.encode("utf-8")),
        "issued_at_epoch_s": now - 1,
        "expires_at_epoch_s": now + 30,
    }
    value = {
        "now": now,
        "anchor": {
            "schema_version": "butler.helper1.execution-trust-anchor.v1",
            "public_key_b64": base64.b64encode(public_key).decode("ascii"),
            "public_key_sha256": digest(public_key),
            "session_digest": "c" * 64,
            "subject_commit": "a" * 40,
            "subject_tree": "b" * 40,
        },
        "receipt": {
            **unsigned,
            "signature_b64": base64.b64encode(
                private_key.sign(canonical_json(unsigned))
            ).decode("ascii"),
        },
        "expected": {
            "requestId": REQUEST_ID,
            "workspaceId": WORKSPACE_ID,
            "generationId": GENERATION_ID,
            "action": "ask",
            "answer": ANSWER,
        },
    }
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
