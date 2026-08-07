from __future__ import annotations

import copy
import hashlib
import inspect
import pickle
import random
from dataclasses import replace
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from butler_pc_core.helper1.approval_closure import (
    ApprovalState,
    EvidenceArtifact,
    FailureCode,
    evaluate_product_closure,
)
from butler_pc_core.helper1.canonical_json import canonicalize_butler_cj1, require_canonical_butler_cj1
from butler_pc_core.helper1.retrieval_policy import (
    ProtectedTrustPolicyProvider,
    RetrievalPolicyAuthority,
    RetrievalPolicyAuthorityError,
)

from .v51_support import (
    activation_authority,
    authority,
    EVIDENCE_KEY_ID,
    envelope,
    evidence_set,
    evidence_set_digest,
    policy_bytes,
    THRESHOLD_KEY_ID,
)


def _closure(tmp_path, *, production: bool = False):
    policy_authority, keys = authority(tmp_path, production=production)
    values = evidence_set(keys)
    activation = activation_authority(keys[2], closure_digest=evidence_set_digest(values))
    verdict = evaluate_product_closure(policy_authority, activation, values)
    return policy_authority, values, activation, verdict


def test_complete_signed_set_reaches_only_its_allowed_state(tmp_path) -> None:
    _, _, _, test_verdict = _closure(tmp_path / "test")
    assert test_verdict.state is ApprovalState.ALL_EVIDENCE_VERIFIED
    assert not test_verdict.release_allowed
    assert test_verdict.failures == ()

    _, _, _, product_verdict = _closure(tmp_path / "product", production=True)
    assert product_verdict.state is ApprovalState.RELEASE_ALLOWED
    assert product_verdict.release_allowed
    assert product_verdict.to_public_dict()["product_release_allowed"] is False


def test_missing_duplicate_and_replayed_roles_fail_closed(tmp_path) -> None:
    policy_authority, values, activation, first = _closure(tmp_path)
    assert first.state is ApprovalState.ALL_EVIDENCE_VERIFIED
    replayed = evaluate_product_closure(policy_authority, activation, values)
    assert FailureCode.EVIDENCE_REPLAY_DETECTED in {item.code for item in replayed.failures}

    missing_values = values[1:]
    other_authority, other_keys = authority(tmp_path / "missing")
    missing_activation = activation_authority(
        other_keys[2], closure_digest=evidence_set_digest(missing_values)
    )
    missing = evaluate_product_closure(other_authority, missing_activation, missing_values)
    assert FailureCode.EVIDENCE_ROLE_MISSING in {item.code for item in missing.failures}

    duplicate_values = values + [values[0]]
    duplicate_authority, duplicate_keys = authority(tmp_path / "duplicate")
    duplicate_activation = activation_authority(
        duplicate_keys[2], closure_digest=evidence_set_digest(duplicate_values)
    )
    duplicate = evaluate_product_closure(
        duplicate_authority, duplicate_activation, duplicate_values
    )
    assert FailureCode.EVIDENCE_ROLE_DUPLICATE in {item.code for item in duplicate.failures}


def test_signature_payload_and_key_role_tampering_are_rejected(tmp_path) -> None:
    policy_authority, keys = authority(tmp_path)
    values = evidence_set(keys)
    payload = require_canonical_butler_cj1(values[0].payload_bytes)
    payload["passed"] = False
    values[0] = replace(values[0], payload_bytes=canonicalize_butler_cj1(payload))

    threshold_payload = require_canonical_butler_cj1(values[-1].payload_bytes)
    values[-1] = envelope(
        role="A4_RETRIEVAL_THRESHOLD_POLICY",
        payload=threshold_payload,
        key_id=EVIDENCE_KEY_ID,
        private_key=keys[0],
        nonce_byte=110,
        attachments=dict(values[-1].attachments_by_digest),
    )

    bad_envelope = require_canonical_butler_cj1(values[1].envelope_bytes)
    bad_envelope["signature_b64u"] = "A" * 86
    values[1] = EvidenceArtifact(
        canonicalize_butler_cj1(bad_envelope),
        values[1].payload_bytes,
        values[1].attachments_by_digest,
    )
    activation = activation_authority(keys[2], closure_digest=evidence_set_digest(values))
    verdict = evaluate_product_closure(policy_authority, activation, values)
    codes = {item.code for item in verdict.failures}
    assert FailureCode.EVIDENCE_PAYLOAD_DIGEST_MISMATCH in codes
    assert FailureCode.EVIDENCE_SIGNATURE_INVALID in codes
    assert FailureCode.EVIDENCE_SEMANTICS_INVALID in codes


@pytest.mark.parametrize("seed", range(1, 101))
def test_deterministic_fake_signatures_are_all_blocked(tmp_path, seed: int) -> None:
    policy_authority, keys = authority(tmp_path / str(seed), repository=f"test/helper1/fake-signature/{seed}")
    values = evidence_set(keys)
    target = values[0]
    wire = require_canonical_butler_cj1(target.envelope_bytes)
    fake = random.Random(seed).randbytes(64)
    wire["signature_b64u"] = __import__("base64").urlsafe_b64encode(fake).rstrip(b"=").decode("ascii")
    values[0] = EvidenceArtifact(
        canonicalize_butler_cj1(wire),
        target.payload_bytes,
        target.attachments_by_digest,
    )
    activation = activation_authority(keys[2], closure_digest=evidence_set_digest(values))
    verdict = evaluate_product_closure(policy_authority, activation, values)
    assert FailureCode.EVIDENCE_SIGNATURE_INVALID in {item.code for item in verdict.failures}


def test_authority_api_does_not_accept_caller_selected_identity_or_clock_value() -> None:
    parameters = inspect.signature(RetrievalPolicyAuthority.from_composition_root).parameters
    assert set(parameters) == {"provider", "replay_store", "clock"}
    source = inspect.getsource(RetrievalPolicyAuthority.from_composition_root)
    assert "SQLiteReplayStore" not in source
    assert "ReplayReservationStore" in source
    forbidden = {"public_key", "expected_commit", "expected_tree", "now", "seen_nonce"}
    assert not forbidden & set(parameters)


def test_authority_snapshot_and_verdict_are_not_copyable_or_serializable(tmp_path) -> None:
    policy_authority, _, _, verdict = _closure(tmp_path)
    for value in (policy_authority, policy_authority.snapshot, verdict):
        with pytest.raises(TypeError):
            copy.copy(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)
    with pytest.raises(AttributeError):
        policy_authority.snapshot.enabled = False
    with pytest.raises(AttributeError):
        verdict.state = ApprovalState.ACTIVE


def test_new_policy_epoch_invalidates_old_authority(tmp_path) -> None:
    repository = "test/helper1/policy-rotation"
    old, _ = authority(tmp_path / "old", epoch=70, repository=repository)
    assert old.is_current()
    new, _ = authority(tmp_path / "new", epoch=71, repository=repository)
    assert new.is_current()
    assert not old.is_current()

    raw, _ = policy_bytes(epoch=69, repository=repository)
    digest = hashlib.sha256(raw).hexdigest()
    provider = ProtectedTrustPolicyProvider._for_test(raw, digest)
    with pytest.raises(RetrievalPolicyAuthorityError, match="TRUST_POLICY_ROLLBACK"):
        provider.load_snapshot()


def test_rfc8032_ed25519_vector_is_supported() -> None:
    source = Path(__file__).with_name("vectors") / "ed25519_rfc8032_subset.json"
    vector = json.loads(source.read_text(encoding="utf-8"))["vectors"][0]
    public = bytes.fromhex(vector["public_key_hex"])
    signature = bytes.fromhex(vector["signature_hex"])
    message = bytes.fromhex(vector["message_hex"])
    Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
    with pytest.raises(InvalidSignature):
        Ed25519PublicKey.from_public_bytes(public).verify(signature, b"x")


def test_signing_input_has_fixed_domain_separator() -> None:
    value = {"a": 1}
    digest = hashlib.sha256(b"BUTLER-HELPER1-EVIDENCE-V1\x00" + canonicalize_butler_cj1(value))
    assert digest.hexdigest() == "1d45a4fa1377d7929145fcc116efee38fdf9a1ea94f71baa57bd9801cbd6aa8b"
