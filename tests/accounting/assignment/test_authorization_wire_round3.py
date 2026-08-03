from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from butler_pc_core.accounting.assignment.authorization import (
    ALGORITHM,
    ASSERTION_TYPE,
    AuthorizationTrustKey,
    AuthorizationTrustPolicy,
    ExistingUserAuthorizationAuthority,
)
from butler_pc_core.accounting.assignment.domain import AssignmentError
from butler_pc_core.auth.capability_token import LocalIpcSession


ROOT = Path(__file__).resolve().parents[3]
VECTOR = json.loads(
    (ROOT / "tests/fixtures/box5_ua2_golden_v1.json").read_text("utf-8")
)


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _authority() -> ExistingUserAuthorizationAuthority:
    trust = AuthorizationTrustPolicy(
        policy_id="BOX5-TEST-UA2-GOLDEN",
        issuer="butler.test.user-authority",
        audience="butler-box5-accounting",
        keys=(
            AuthorizationTrustKey(
                key_id="BOX5-TEST-UA2-GOLDEN-20260803",
                public_key=_decode(VECTOR["public_key_b64url"]),
                status="ACTIVE",
            ),
        ),
        policy_digest="a" * 64,
        not_before_epoch_s=1_899_999_000,
        not_after_epoch_s=1_900_001_000,
    )
    return ExistingUserAuthorizationAuthority(trust)


def _session() -> LocalIpcSession:
    from datetime import datetime, timezone

    return LocalIpcSession(
        session_id="session-golden",
        device_id="device-golden",
        session_digest="s" * 64,
        device_binding_digest="d" * 64,
        audience="butler-local-sidecar-ipc",
        expires_at=datetime.fromtimestamp(1_900_001_000, timezone.utc),
    )


def _verify(token: str):
    return _authority().verify(
        token,
        local_session=_session(),
        profile=SimpleNamespace(
            status="ACTIVE",
            profile_id="tenant-golden",
            profile_digest="company-golden",
        ),
        action="ASSIGNMENT_CREATE",
        resource_type="ACCOUNTING_TRANSACTION",
        resource_id="txn-golden-001",
        now_epoch_s=1_900_000_001,
    )


def test_normative_golden_vector_is_exact_and_schema_valid() -> None:
    protected_segment, payload_segment, signature_segment = VECTOR["compact"].split(".")
    assert json.loads(_decode(protected_segment)) == VECTOR["protected"]
    assert json.loads(_decode(payload_segment)) == VECTOR["payload"]
    assert len(_decode(signature_segment)) == 64

    contracts = ROOT / "butler_pc_core/accounting/assignment/contracts"
    protected_schema = json.loads(
        (contracts / "protected-header-v2.schema.json").read_text("utf-8")
    )
    payload_schema = json.loads(
        (contracts / "user-assertion-v2.schema.json").read_text("utf-8")
    )
    jsonschema.Draft202012Validator(protected_schema).validate(VECTOR["protected"])
    jsonschema.Draft202012Validator(payload_schema).validate(VECTOR["payload"])

    decision = _verify(VECTOR["compact"])
    assert decision.decision_id == VECTOR["payload"]["jti"]
    assert decision.authorization_resource == VECTOR["payload"]["resource"]
    assert decision.assertion_digest == hashlib.sha256(
        VECTOR["compact"].encode("ascii")
    ).hexdigest()


def test_malformed_and_ambiguous_compact_corpus_is_rejected() -> None:
    protected, payload, signature = VECTOR["compact"].split(".")
    duplicate_header = (
        b'{"alg":"EdDSA","kid":"BOX5-TEST-UA2-GOLDEN-20260803",'
        b'"kid":"BOX5-TEST-UA2-GOLDEN-20260803","typ":"BUTLER-UA2"}'
    )
    noncanonical_payload = _decode(payload) + b" "
    flipped = bytearray(_decode(signature))
    flipped[0] ^= 1
    corpus = {
        "two_segments": protected + "." + payload,
        "four_segments": VECTOR["compact"] + ".extra",
        "padded": protected + "=." + payload + "." + signature,
        "whitespace": " " + VECTOR["compact"],
        "invalid_base64url": "!" + protected[1:] + "." + payload + "." + signature,
        "duplicate_key": _b64(duplicate_header) + "." + payload + "." + signature,
        "noncanonical_json": protected + "." + _b64(noncanonical_payload) + "." + signature,
        "short_signature": protected + "." + payload + "." + _b64(b"x" * 63),
        "signature_bit_flip": protected + "." + payload + "." + _b64(bytes(flipped)),
    }
    for name, token in corpus.items():
        with pytest.raises(AssignmentError, match="USER_ASSERTION_INVALID"):
            _verify(token)


def test_resource_normalization_and_wildcard_variants_are_rejected() -> None:
    for resource_id in (
        "*",
        "txn%2Dgolden%2D001",
        "txn//golden",
        "txn/../golden",
        "ｔｘｎ-golden-001",
        "Txn-golden-001",
    ):
        with pytest.raises(AssignmentError, match="AUTHORIZATION_RESOURCE_MISMATCH"):
            _authority().verify(
                VECTOR["compact"],
                local_session=_session(),
                profile=SimpleNamespace(
                    status="ACTIVE",
                    profile_id="tenant-golden",
                    profile_digest="company-golden",
                ),
                action="ASSIGNMENT_CREATE",
                resource_type="ACCOUNTING_TRANSACTION",
                resource_id=resource_id,
                now_epoch_s=1_900_000_001,
            )


def test_wire_constants_do_not_drift_from_contract() -> None:
    assert ALGORITHM == "EdDSA"
    assert ASSERTION_TYPE == "BUTLER-UA2"
    assert set(VECTOR["payload"]) == {
        "ver",
        "iss",
        "aud",
        "sub",
        "tenant_id",
        "company_id",
        "device_id",
        "session_id",
        "action",
        "resource",
        "iat",
        "nbf",
        "exp",
        "jti",
        "nonce",
        "policy_id",
        "kid",
        "alg",
    }
