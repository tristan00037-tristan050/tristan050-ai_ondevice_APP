from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from butler_pc_core.helper1.approval_closure import (
    EvidenceArtifact,
    FailureCode,
    evaluate_product_closure,
)
from butler_pc_core.helper1.canonical_json import canonicalize_butler_cj1, require_canonical_butler_cj1

from .v51_support import (
    EVIDENCE_KEY_ID,
    NOW,
    activation_authority,
    authority,
    b64url,
    envelope,
    evidence_set,
    evidence_set_digest,
)


def _evaluate(tmp_path, values, keys):
    policy_authority, _ = authority(tmp_path)
    activation = activation_authority(keys[2], closure_digest=evidence_set_digest(values))
    return evaluate_product_closure(policy_authority, activation, values)


def _wire(item: EvidenceArtifact) -> dict:
    return require_canonical_butler_cj1(item.envelope_bytes)


def _payload(item: EvidenceArtifact) -> dict:
    return require_canonical_butler_cj1(item.payload_bytes)


def test_payload_is_detached_and_one_byte_change_breaks_digest(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    assert set(_wire(values[0])) == {"signed", "signature_algorithm", "signature_b64u"}
    payload = _payload(values[0])
    payload["passed"] = False
    values[0] = replace(values[0], payload_bytes=canonicalize_butler_cj1(payload))
    verdict = _evaluate(tmp_path / "eval", values, keys)
    codes = {item.code for item in verdict.failures}
    assert FailureCode.EVIDENCE_PAYLOAD_DIGEST_MISMATCH in codes
    assert FailureCode.EVIDENCE_SEMANTICS_INVALID in codes


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "A2_SUBJECT_BINDING_RECEIPT"),
        ("commit_sha", "f" * 40),
        ("tree_sha", "e" * 40),
        ("key_id", "butler/helper1/unpinned/v51"),
        ("issued_at_epoch_s", NOW + 60),
        ("expires_at_epoch_s", NOW - 1),
        ("nonce_b64u", b64url(b"x" * 16)),
    ],
)
def test_signed_field_tampering_never_closes(tmp_path, field: str, value: object) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    target = values[0]
    wire = _wire(target)
    wire["signed"][field] = value
    if field == "role":
        wire["signed"]["payload_media_type"] = "application/vnd.butler.helper1.a2-subject+json;v=1"
    values[0] = EvidenceArtifact(
        canonicalize_butler_cj1(wire), target.payload_bytes, target.attachments_by_digest
    )
    verdict = _evaluate(tmp_path / "eval", values, keys)
    assert verdict.failures
    assert not verdict.release_allowed


def test_unpinned_key_is_rejected_even_with_valid_ed25519_signature(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    target = values[0]
    values[0] = envelope(
        role=_wire(target)["signed"]["role"],
        payload=_payload(target),
        key_id="butler/helper1/unpinned/v51",
        private_key=keys[2],
        nonce_byte=120,
        attachments=dict(target.attachments_by_digest),
    )
    verdict = _evaluate(tmp_path / "eval", values, keys)
    assert FailureCode.EVIDENCE_SIGNATURE_INVALID in {item.code for item in verdict.failures}


def test_resigned_wrong_subject_is_rejected(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    target = values[0]
    role = _wire(target)["signed"]["role"]
    values[0] = envelope(
        role=role,
        payload=_payload(target),
        key_id=EVIDENCE_KEY_ID,
        private_key=keys[0],
        nonce_byte=121,
        attachments=dict(target.attachments_by_digest),
        signed_updates={"commit_sha": "f" * 40},
    )
    verdict = _evaluate(tmp_path / "eval", values, keys)
    assert FailureCode.EVIDENCE_SUBJECT_MISMATCH in {item.code for item in verdict.failures}


def test_attachment_missing_and_digest_mismatch_are_distinct(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    original = evidence_set(keys)

    missing_values = list(original)
    target = missing_values[0]
    missing_values[0] = replace(target, attachments_by_digest=())
    missing = _evaluate(tmp_path / "missing", missing_values, keys)
    assert FailureCode.EVIDENCE_ATTACHMENT_MISSING in {item.code for item in missing.failures}

    mismatch_values = evidence_set(keys)
    target = mismatch_values[0]
    digest, raw = target.attachments_by_digest[0]
    mismatch_values[0] = replace(target, attachments_by_digest=((digest, raw + b"x"),))
    mismatch = _evaluate(tmp_path / "mismatch", mismatch_values, keys)
    assert FailureCode.EVIDENCE_ATTACHMENT_DIGEST_MISMATCH in {item.code for item in mismatch.failures}


def test_unknown_envelope_field_is_not_ignored(tmp_path) -> None:
    _, keys = authority(tmp_path / "keys")
    values = evidence_set(keys)
    target = values[0]
    wire = _wire(target)
    wire["approved"] = True
    values[0] = EvidenceArtifact(
        canonicalize_butler_cj1(wire), target.payload_bytes, target.attachments_by_digest
    )
    activation = activation_authority(keys[2], closure_digest=hashlib.sha256(b"invalid").hexdigest())
    verdict = evaluate_product_closure(authority(tmp_path / "eval")[0], activation, values)
    assert FailureCode.EVIDENCE_SCHEMA_INVALID in {item.code for item in verdict.failures}
