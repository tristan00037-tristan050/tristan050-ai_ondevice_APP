from __future__ import annotations

from dataclasses import replace

from ac25.strict_v44 import validate_strict_receipt
from tests.box5_ac25.v44_fixtures import policy_document, valid_input


def _codes(inp):
    return validate_strict_receipt(inp).failures


def test_missing_authority_policy_fails_closed():
    inp = replace(valid_input(), authority_policy_bytes=b"")
    assert _codes(inp) == ("AUTHORITY_POLICY_NOT_PROVISIONED",)


def test_candidate_authored_policy_rejected():
    original = valid_input()
    inp = replace(original, authority_source=replace(original.authority_source, candidate_controlled=True))
    assert "AUTHORITY_POLICY_SELF_AUTHORED" in _codes(inp)


def test_policy_source_blob_must_match():
    original = valid_input()
    bad_source = replace(original.authority_source.source, blob_oid="0" * 40)
    inp = replace(original, authority_source=replace(original.authority_source, source=bad_source))
    assert "AUTHORITY_POLICY_SOURCE_UNTRUSTED" in _codes(inp)


def test_policy_repository_id_must_match():
    original = valid_input()
    candidate = replace(original.candidate_bundle, repository_id=42)
    assert "AUTHORITY_POLICY_COORDINATE_MISMATCH" in _codes(replace(original, candidate_bundle=candidate))


def test_policy_start_head_tree_must_match():
    original = valid_input()
    candidate = replace(original.candidate_bundle, start_tree="0" * 40)
    assert "AUTHORITY_POLICY_COORDINATE_MISMATCH" in _codes(replace(original, candidate_bundle=candidate))


def test_policy_candidate_head_tree_must_match():
    original = valid_input()
    candidate = replace(original.candidate_bundle, candidate_tree="0" * 40)
    assert "AUTHORITY_POLICY_COORDINATE_MISMATCH" in _codes(replace(original, candidate_bundle=candidate))


def test_policy_invalidated_when_candidate_head_moves():
    original = valid_input()
    candidate = replace(original.candidate_bundle, candidate_head="0" * 40)
    assert "AUTHORITY_POLICY_COORDINATE_MISMATCH" in _codes(replace(original, candidate_bundle=candidate))


def test_policy_issued_after_authority_run_start_rejected():
    document = policy_document()
    document["issued_at"] = "2026-08-08T00:00:02Z"
    assert "REMOTE_TIME_ORDER_INVALID" in _codes(valid_input(document))


def test_expired_policy_rejected():
    original = valid_input()
    inp = replace(original, now_utc="2026-08-10T00:00:00Z")
    assert "AUTHORITY_POLICY_EXPIRED" in _codes(inp)


def test_inventory_digest_mismatch_rejected():
    original = valid_input()
    candidate = replace(original.candidate_bundle, changed_paths_sha256="0" * 64)
    assert "AUTHORITY_POLICY_COORDINATE_MISMATCH" in _codes(replace(original, candidate_bundle=candidate))


def test_valid_protected_policy_passes():
    verdict = validate_strict_receipt(valid_input())
    assert verdict.ok is True
    assert verdict.failures == ()
    assert verdict.offending_items == ()
