from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from butler_pc_core.firstscreen_trust import (
    BootstrapRoot,
    TrustVerificationError,
    build_context_digest,
    canonical_json,
    document_digest,
    key_id_for_public_key,
    sign_document,
    strict_json_loads,
    signature_message,
    trusted_state,
    validate_build_context,
    verify_release_subjects,
    verify_revocations,
    verify_risk_decision,
    verify_root_chain,
)
from butler_pc_core.firstscreen_runtime_trust import (
    InMemoryRuntimeTrustStateStore,
    RuntimeTrustError,
    verify_and_advance_runtime_trust,
)


pytestmark = pytest.mark.no_sidecar_token
NOW = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)


def key():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    return private, key_id_for_public_key(public), base64.urlsafe_b64encode(public).decode().rstrip("=")


def encoded(value: object) -> bytes:
    return canonical_json(value)


def policy(root_count: int = 1, threshold: int = 1):
    roots = [key() for _ in range(root_count)]
    risk = key()
    revocation = key()
    release = key()
    keys = {
        key_id: {"algorithm": "ed25519", "public_key": public}
        for _private, key_id, public in [*roots, risk, revocation, release]
    }
    document = {
        "schema_version": "butler.firstscreen.root-policy.v1",
        "policy_id": "butler-firstscreen-trust",
        "version": 1,
        "expires_at_utc": "2027-07-21T00:00:00Z",
        "consistent_snapshot": True,
        "keys": keys,
        "roles": {
            "root": {"key_ids": [item[1] for item in roots], "threshold": threshold},
            "risk-decision": {"key_ids": [risk[1]], "threshold": 1},
            "revocation": {"key_ids": [revocation[1]], "threshold": 1},
            "release": {"key_ids": [release[1]], "threshold": 1},
        },
        "previous_root_digest": None,
        "signatures": [],
    }
    document["signatures"] = [sign_document("root-policy", document, item[0], item[1]) for item in roots[:threshold]]
    anchor = BootstrapRoot(document_digest(document))
    verified = verify_root_chain(anchor, encoded(document), now=NOW)
    return document, verified, anchor, {"roots": roots, "risk": risk, "revocation": revocation, "release": release}


def revocations(root, anchor, keys, **updates):
    document = {
        "schema_version": "butler.firstscreen.revocations.v2",
        "policy_id": "butler-firstscreen-trust",
        "version": 1,
        "generated_at_utc": "2026-07-21T00:00:00Z",
        "expires_at_utc": "2026-08-21T00:00:00Z",
        "previous_digest": None,
        "root_policy_digest": root.digest,
        "revoked_decision_ids": [],
        "revoked_key_ids": [],
        "revoked_epochs": [],
        "signatures": [],
    }
    document.update(updates)
    document["signatures"] = [sign_document("revocations", document, keys["revocation"][0], keys["revocation"][1])]
    return document, verify_revocations(root, encoded(document), bootstrap=anchor, now=NOW)


def decision(root, revoked, keys, **updates):
    document = {
        "schema_version": "butler.firstscreen.risk-decision.v2",
        "policy_id": "butler-firstscreen-trust",
        "decision_id": "STORAGE_RISK_FS_V2_5_001",
        "version": 1,
        "approved_at_utc": "2026-07-21T00:00:00Z",
        "expires_at_utc": "2026-08-01T00:00:00Z",
        "scope": ["CONVERSATION_TITLE", "FTS_TITLE_INDEX"],
        "protection_boundary": ["ON_DEVICE", "OS_USER_BOUNDARY", "APP_DATA_PATH", "OWNER_MODE_GUARD"],
        "data_classification": "CONFIDENTIAL",
        "owner_role": "ATLINK_REPRESENTATIVE",
        "revocation_epoch": 0,
        "root_policy_digest": root.digest,
        "source_blob_digest": "b" * 64,
        "canonical_ssot_location": "docs/product/firstscreen_v2_5/risk-decision.json",
        "signatures": [],
    }
    document.update(updates)
    document["signatures"] = [sign_document("risk-decision", document, keys["risk"][0], keys["risk"][1])]
    return document, verify_risk_decision(root, revoked, encoded(document), now=NOW)


@pytest.mark.parametrize(
    "raw,code",
    [
        (b'{"a":1,"a":2}', "BLOCK_JSON_DUPLICATE_KEY"),
        (b'{"a":1.0}', "BLOCK_JSON_NUMBER"),
        (b'{"a":NaN}', "BLOCK_JSON_NUMBER"),
        (b'{"a":Infinity}', "BLOCK_JSON_NUMBER"),
        (b'\xef\xbb\xbf{}', "BLOCK_JSON_RESOURCE_LIMIT"),
        (b'[]', "BLOCK_JSON_OBJECT_REQUIRED"),
        (b'\xff', "BLOCK_JSON_PARSE"),
        (b'', "BLOCK_JSON_RESOURCE_LIMIT"),
    ],
    ids=["CR-001", "CR-002-float", "CR-002-nan", "CR-002-infinity", "CR-BOM", "CR-root-array", "CR-UTF8", "CR-empty"],
)
def test_strict_parser_attacks(raw: bytes, code: str) -> None:
    with pytest.raises(TrustVerificationError, match=code):
        strict_json_loads(raw)


def test_resource_depth_and_canonical_type_limits() -> None:
    nested = b'{"x":' * 30 + b'0' + b'}' * 30
    with pytest.raises(TrustVerificationError, match="BLOCK_JSON_RESOURCE_LIMIT"):
        strict_json_loads(nested)
    with pytest.raises(TrustVerificationError, match="BLOCK_JSON_CANONICALIZATION"):
        canonical_json({1: "integer-key", "2": "string-key"})


@pytest.mark.parametrize("operation", ["domain", "public-key", "signing-key-id"], ids=["CR-domain", "CR-public-key", "CR-signing-key-id"])
def test_crypto_input_boundaries(operation: str) -> None:
    if operation == "domain":
        with pytest.raises(TrustVerificationError, match="BLOCK_SIGNATURE_DOMAIN"):
            signature_message("", {})
    elif operation == "public-key":
        with pytest.raises(TrustVerificationError, match="BLOCK_PUBLIC_KEY"):
            key_id_for_public_key(b"short")
    else:
        private = Ed25519PrivateKey.generate()
        with pytest.raises(TrustVerificationError, match="BLOCK_SIGNATURE_KEY_ID"):
            sign_document("root-policy", {"schema_version": "x", "signatures": []}, private, "invalid")


def test_non_ascii_signature_domain_is_a_stable_block() -> None:
    with pytest.raises(TrustVerificationError, match="BLOCK_SIGNATURE_DOMAIN"):
        signature_message("위험결정", {"schema_version": "v1", "signatures": []})


def test_tr_001_bundle_key_substitution_cannot_replace_bootstrap() -> None:
    _document, _root, anchor, _keys = policy()
    attacker_document, _attacker_root, _attacker_anchor, _attacker_keys = policy()
    with pytest.raises(TrustVerificationError, match="BLOCK_BOOTSTRAP_ROOT_MISMATCH"):
        verify_root_chain(anchor, encoded(attacker_document), now=NOW)


@pytest.mark.parametrize(
    "root_count,threshold,present,code",
    [(3, 2, 0, "BLOCK_ROOT_SCHEMA"), (3, 2, 1, "BLOCK_ROOT_THRESHOLD"), (3, 3, 2, "BLOCK_ROOT_THRESHOLD")],
    ids=["TR-003-none", "TR-003-one", "TR-003-two"],
)
def test_threshold_shortfall_blocks(root_count: int, threshold: int, present: int, code: str) -> None:
    document, _root, _anchor, keys = policy(root_count, threshold)
    document["signatures"] = [sign_document("root-policy", document, item[0], item[1]) for item in keys["roots"][:present]]
    anchor = BootstrapRoot(document_digest(document))
    with pytest.raises(TrustVerificationError, match=code):
        verify_root_chain(anchor, encoded(document), now=NOW)


def test_tr_004_duplicate_signature_does_not_fill_threshold() -> None:
    document, _root, _anchor, keys = policy(3, 2)
    one = sign_document("root-policy", document, keys["roots"][0][0], keys["roots"][0][1])
    document["signatures"] = [one, one]
    anchor = BootstrapRoot(document_digest(document))
    with pytest.raises(TrustVerificationError, match="BLOCK_ROOT_THRESHOLD"):
        verify_root_chain(anchor, encoded(document), now=NOW)


def test_tr_005_tr_006_rotation_requires_old_and_new_thresholds() -> None:
    _old_doc, old, anchor, old_keys = policy()
    new_doc, _new, _new_anchor, new_keys = policy()
    new_doc["version"] = 2
    new_doc["previous_root_digest"] = old.digest
    new_only = sign_document("root-policy", new_doc, new_keys["roots"][0][0], new_keys["roots"][0][1])
    new_doc["signatures"] = [new_only]
    with pytest.raises(TrustVerificationError, match="BLOCK_ROTATION_OLD_THRESHOLD"):
        verify_root_chain(anchor, encoded(new_doc), trusted=old, now=NOW)
    old_only = sign_document("root-policy", new_doc, old_keys["roots"][0][0], old_keys["roots"][0][1])
    new_doc["signatures"] = [old_only]
    with pytest.raises(TrustVerificationError, match="BLOCK_ROTATION_NEW_THRESHOLD"):
        verify_root_chain(anchor, encoded(new_doc), trusted=old, now=NOW)
    new_doc["signatures"] = [old_only, new_only]
    assert verify_root_chain(anchor, encoded(new_doc), trusted=old, now=NOW).version == 2


def test_release_pin_membership_cannot_replace_old_root_threshold() -> None:
    old_document, old, anchor, old_keys = policy()
    attacker_one = key()
    attacker_two = key()
    old_root = old_keys["roots"][0]
    candidate_keys = [old_root, attacker_one, attacker_two]
    candidate = {
        **copy.deepcopy(old_document),
        "version": 2,
        "keys": {
            item[1]: {"algorithm": "ed25519", "public_key": item[2]}
            for item in candidate_keys
        },
        "roles": {
            name: {"key_ids": [item[1] for item in candidate_keys], "threshold": 2}
            for name in ("root", "risk-decision", "revocation", "release")
        },
        "previous_root_digest": old.digest,
        "signatures": [],
    }
    candidate["signatures"] = [
        sign_document("root-policy", candidate, item[0], item[1])
        for item in (attacker_one, attacker_two)
    ]
    with pytest.raises(TrustVerificationError, match="BLOCK_ROTATION_OLD_THRESHOLD"):
        verify_root_chain(anchor, encoded(candidate), trusted=old, now=NOW)


@pytest.mark.parametrize("version,code", [(1, "BLOCK_ROOT_ROLLBACK"), (3, "BLOCK_ROOT_VERSION_GAP"), (8, "BLOCK_ROOT_VERSION_GAP")], ids=["TR-008", "TR-007-gap", "TR-007-fast-forward"])
def test_root_version_attacks(version: int, code: str) -> None:
    _document, root, anchor, keys = policy()
    candidate = copy.deepcopy(root.document)
    candidate["version"] = version
    candidate["previous_root_digest"] = root.digest
    candidate["signatures"] = [sign_document("root-policy", candidate, keys["roots"][0][0], keys["roots"][0][1])]
    with pytest.raises(TrustVerificationError, match=code):
        verify_root_chain(anchor, encoded(candidate), trusted=root, now=NOW)


def test_tr_009_expired_root_blocks() -> None:
    document, _root, _anchor, keys = policy()
    document["expires_at_utc"] = "2026-07-21T12:00:00Z"
    document["signatures"] = [sign_document("root-policy", document, keys["roots"][0][0], keys["roots"][0][1])]
    anchor = BootstrapRoot(document_digest(document))
    with pytest.raises(TrustVerificationError, match="BLOCK_ROOT_EXPIRED"):
        verify_root_chain(anchor, encoded(document), now=NOW)


@pytest.mark.parametrize(
    "updates,code",
    [
        ({"expires_at_utc": "2026-07-21T12:00:00Z"}, "BLOCK_REVOCATION_EXPIRED"),
        ({"root_policy_digest": "0" * 64}, "BLOCK_REVOCATION_ROOT"),
        ({"previous_digest": "0" * 64}, "BLOCK_REVOCATION_ROLLBACK"),
    ],
    ids=["RV-006", "RV-root-mix", "RV-010-genesis"],
)
def test_revocation_metadata_attacks(updates, code) -> None:
    _doc, root, anchor, keys = policy()
    document = {
        "schema_version": "butler.firstscreen.revocations.v2", "policy_id": "butler-firstscreen-trust",
        "version": 1, "generated_at_utc": "2026-07-21T00:00:00Z", "expires_at_utc": "2026-08-21T00:00:00Z",
        "previous_digest": None, "root_policy_digest": root.digest, "revoked_decision_ids": [], "revoked_key_ids": [],
        "revoked_epochs": [], "signatures": [],
    }
    document.update(updates)
    document["signatures"] = [sign_document("revocations", document, keys["revocation"][0], keys["revocation"][1])]
    with pytest.raises(TrustVerificationError, match=code):
        verify_revocations(root, encoded(document), bootstrap=anchor, now=NOW)


@pytest.mark.parametrize("field,value", [("revoked_decision_ids", []), ("revoked_key_ids", []), ("revoked_epochs", [])], ids=["RV-001", "RV-002", "RV-003"])
def test_revocation_deletion_is_detected(field: str, value: list) -> None:
    _doc, root, anchor, keys = policy()
    first_updates = {
        "revoked_decision_ids": ["old-decision"],
        "revoked_key_ids": [keys["risk"][1]],
        "revoked_epochs": [7],
    }
    first_doc, first = revocations(root, anchor, keys, **first_updates)
    next_doc = copy.deepcopy(first_doc)
    next_doc["version"] = 2
    next_doc["previous_digest"] = first.digest
    next_doc[field] = value
    next_doc["signatures"] = [sign_document("revocations", next_doc, keys["revocation"][0], keys["revocation"][1])]
    with pytest.raises(TrustVerificationError, match="BLOCK_REVOCATION_WEAKENED"):
        verify_revocations(root, encoded(next_doc), bootstrap=anchor, current_state=trusted_state(root, first), previous=first, now=NOW)


@pytest.mark.parametrize(
    "updates,code",
    [
        ({"expires_at_utc": "2026-07-21T12:00:00Z"}, "BLOCK_DECISION_EXPIRED"),
        ({"scope": ["CONVERSATION_TITLE"]}, "BLOCK_DECISION_SCOPE"),
        ({"owner_role": "ATTACKER"}, "BLOCK_DECISION_SCOPE"),
        ({"root_policy_digest": "0" * 64}, "BLOCK_DECISION_ROOT"),
        ({"canonical_ssot_location": "../attack.json"}, "BLOCK_DECISION_SCHEMA"),
    ],
    ids=["decision-expiry", "decision-scope", "decision-owner", "decision-root", "decision-path"],
)
def test_decision_mutations_block(updates, code) -> None:
    _doc, root, anchor, keys = policy()
    _rev_doc, revoked = revocations(root, anchor, keys)
    document, _verified = decision(root, revoked, keys)
    document.update(updates)
    document["signatures"] = [sign_document("risk-decision", document, keys["risk"][0], keys["risk"][1])]
    with pytest.raises(TrustVerificationError, match=code):
        verify_risk_decision(root, revoked, encoded(document), now=NOW)


@pytest.mark.parametrize("kind", ["decision", "key", "epoch"], ids=["decision-revoked", "key-revoked", "epoch-revoked"])
def test_revoked_decision_key_and_epoch_block(kind: str) -> None:
    _doc, root, anchor, keys = policy()
    updates = {
        "revoked_decision_ids": ["STORAGE_RISK_FS_V2_5_001"] if kind == "decision" else [],
        "revoked_key_ids": [keys["risk"][1]] if kind == "key" else [],
        "revoked_epochs": [0] if kind == "epoch" else [],
    }
    _rev_doc, revoked = revocations(root, anchor, keys, **updates)
    expected = "BLOCK_DECISION_THRESHOLD" if kind == "key" else "BLOCK_DECISION_REVOKED"
    with pytest.raises(TrustVerificationError, match=expected):
        decision(root, revoked, keys)


def test_invalid_revoked_metadata_cannot_dos_valid_decision() -> None:
    _doc, root, anchor, keys = policy()
    _rev_doc, revoked = revocations(root, anchor, keys, revoked_key_ids=[keys["roots"][0][1]])
    document, _verified = decision(root, revoked, keys)
    document["signatures"].append({
        "key_id": keys["roots"][0][1],
        "signature": base64.urlsafe_b64encode(b"invalid".ljust(64, b"\0")).decode().rstrip("="),
    })
    assert verify_risk_decision(root, revoked, encoded(document), now=NOW).decision_id == document["decision_id"]


def test_cr_005_signature_domain_replay_blocks() -> None:
    _doc, root, anchor, keys = policy()
    _rev_doc, revoked = revocations(root, anchor, keys)
    document, _verified = decision(root, revoked, keys)
    document["signatures"] = [sign_document("release-subjects", document, keys["risk"][0], keys["risk"][1])]
    with pytest.raises(TrustVerificationError, match="BLOCK_DECISION_THRESHOLD"):
        verify_risk_decision(root, revoked, encoded(document), now=NOW)


def context():
    return {
        "schema_version": "butler.firstscreen.build-context.v1", "mode": "production", "repository": "atlink/butler",
        "commit_oid": "1" * 40, "tree_oid": "2" * 40, "source_manifest_digest": "3" * 64,
        "python_lock_digest": "4" * 64, "npm_lock_digest": "5" * 64, "cargo_lock_digest": "6" * 64,
        "toolchain_identity": "python=3.12.11;node=22.17;rust=1.90", "workflow_identity": "atlink/butler/.github/workflows/firstscreen-v2-5.yml@refs/heads/main",
        "created_at_utc": "2026-07-21T00:00:00Z",
    }


@pytest.mark.parametrize("field,value", [("mode", "development"), ("commit_oid", "dev"), ("tree_oid", "unknown"), ("repository", "attacker")], ids=["BI-mode", "BI-005", "BI-tree", "BI-repository"])
def test_build_context_fail_closed(field: str, value: str) -> None:
    document = context()
    document[field] = value
    with pytest.raises(TrustVerificationError):
        validate_build_context(document)


@pytest.mark.parametrize("field", ["commit_oid", "tree_oid"])
def test_build_context_rejects_numeric_object_ids(field: str) -> None:
    document = context()
    document[field] = int("1" * 40)
    with pytest.raises(TrustVerificationError, match="BLOCK_BUILD_CONTEXT_IDENTITY"):
        validate_build_context(document)


def test_release_subjects_bind_all_four_artifacts_and_release_role() -> None:
    _doc, root, _anchor, keys = policy()
    digest = build_context_digest(context())
    artifacts = {name: name.encode() for name in ("source_archive", "web_dist_archive", "macos_artifact", "sbom")}
    subjects = {
        name: {"name": f"{name}.bin", "size": len(payload), "sha256": __import__("hashlib").sha256(payload).hexdigest(), "build_context_digest": digest}
        for name, payload in artifacts.items()
    }
    document = {
        "schema_version": "butler.firstscreen.release-subjects.v1", "policy_id": "butler-firstscreen-trust",
        "build_context_digest": digest, "subjects": subjects, "created_at_utc": "2026-07-21T00:00:00Z", "signatures": [],
    }
    document["signatures"] = [sign_document("release-subjects", document, keys["release"][0], keys["release"][1])]
    assert verify_release_subjects(root, encoded(document), expected_build_context_digest=digest, artifacts=artifacts, now=NOW)
    for logical_name in artifacts:
        forged = dict(artifacts)
        forged[logical_name] += b"x"
        with pytest.raises(TrustVerificationError, match="BLOCK_RELEASE_SUBJECT_MISMATCH"):
            verify_release_subjects(root, encoded(document), expected_build_context_digest=digest, artifacts=forged, now=NOW)


def _runtime_inputs():
    root_document, root, _anchor, keys = policy()
    revocation_document, revocation = revocations(root, _anchor, keys)
    decision_document, _verified_decision = decision(root, revocation, keys)
    context_document = context()
    context_digest = build_context_digest(context_document)
    artifacts = {name: name.encode() for name in ("source_archive", "web_dist_archive", "macos_artifact", "sbom")}
    subjects = {
        name: {
            "name": f"{name}.bin", "size": len(payload),
            "sha256": __import__("hashlib").sha256(payload).hexdigest(),
            "build_context_digest": context_digest,
        }
        for name, payload in artifacts.items()
    }
    release = {
        "schema_version": "butler.firstscreen.release-subjects.v1",
        "policy_id": "butler-firstscreen-trust",
        "build_context_digest": context_digest,
        "subjects": subjects,
        "created_at_utc": "2026-07-21T00:00:00Z",
        "signatures": [],
    }
    release["signatures"] = [sign_document("release-subjects", release, keys["release"][0], keys["release"][1])]
    owner_public = root_document["keys"][keys["roots"][0][1]]["public_key"]
    raw_public = base64.urlsafe_b64decode(owner_public + "=" * ((4 - len(owner_public) % 4) % 4))
    fingerprint = "SHA256:" + base64.b64encode(__import__("hashlib").sha256(raw_public).digest()).decode().rstrip("=")
    pin = {
        "schema_version": "butler.firstscreen.external-root-pin.v1",
        "phase": "development",
        "root_fingerprint": fingerprint,
    }
    return {
        "root_bytes": encoded(root_document),
        "revocation_bytes": encoded(revocation_document),
        "decision_bytes": encoded(decision_document),
        "build_context_bytes": encoded(context_document),
        "release_subjects_bytes": encoded(release),
        "artifacts": artifacts,
        "external_pin_bytes": encoded(pin),
        "expected_owner_fingerprint": fingerprint,
    }


def test_runtime_receipt_is_single_authority_monotonic_and_activation_closed() -> None:
    inputs = _runtime_inputs()
    store = InMemoryRuntimeTrustStateStore()
    first = verify_and_advance_runtime_trust(**inputs, store=store, now=NOW)
    second = verify_and_advance_runtime_trust(**inputs, store=store, now=NOW)
    assert first["schema_version"] == "butler.firstscreen.runtime-trust-receipt.v1"
    assert first["runtime_activation_allowed"] is False
    assert second == first


def test_runtime_keychain_state_blocks_rollback_and_cas_conflict() -> None:
    inputs = _runtime_inputs()
    store = InMemoryRuntimeTrustStateStore()
    verify_and_advance_runtime_trust(**inputs, store=store, now=NOW)
    assert store.value is not None
    store.value["root_version"] = 2
    with pytest.raises(RuntimeTrustError, match="BLOCK_TRUST_STATE_MISSING_OR_ROLLBACK"):
        verify_and_advance_runtime_trust(**inputs, store=store, now=NOW)

    class ConflictStore(InMemoryRuntimeTrustStateStore):
        def compare_and_swap(self, expected_digest, replacement):
            return False

    with pytest.raises(RuntimeTrustError, match="BLOCK_KEYCHAIN_CAS_CONFLICT"):
        verify_and_advance_runtime_trust(**inputs, store=ConflictStore(), now=NOW)


def test_signature_metadata_resource_exhaustion_is_bounded() -> None:
    document, _root, _anchor, keys = policy()
    one = sign_document("root-policy", document, keys["roots"][0][0], keys["roots"][0][1])
    document["signatures"] = [one] * 17
    with pytest.raises(TrustVerificationError, match="BLOCK_ROOT_SCHEMA"):
        verify_root_chain(BootstrapRoot(document_digest(document)), encoded(document), now=NOW)
