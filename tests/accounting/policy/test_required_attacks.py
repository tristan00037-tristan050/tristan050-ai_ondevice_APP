from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from butler_pc_core.accounting.policy import (
    DRAFT_MANIFEST_RAW_SHA256,
    PolicyLoadError,
    PolicyRuntime,
    bundled_draft_path,
    load_bundled_draft,
    load_policy_bundle,
    load_policy_document,
)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _assert_error(exc: pytest.ExceptionInfo[PolicyLoadError], expected: str) -> None:
    assert str(exc.value) == expected
    assert f"{exc.value.fail_class}:{exc.value.detail_id}" == expected


def test_policy_atk_01_duplicate_json_key() -> None:
    raw = b'{"rule_id":"A","rule_id":"B"}'
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_document(raw, _digest(raw))
    _assert_error(exc, "POLICY_SCHEMA:DUPLICATE_JSON_KEY")


@pytest.mark.parametrize("literal", [b"NaN", b"Infinity", b"-Infinity"])
def test_policy_atk_02_nonfinite_number(literal: bytes) -> None:
    raw = b'{"amount":' + literal + b"}"
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_document(raw, _digest(raw))
    _assert_error(exc, "POLICY_SCHEMA:NONFINITE_NUMBER")


def test_policy_atk_03_float_in_policy() -> None:
    raw = b'{"amount":1.25}'
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_document(raw, _digest(raw))
    _assert_error(exc, "POLICY_SCHEMA:FLOAT_IN_POLICY")


def test_policy_atk_04_digest_mismatch() -> None:
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_document(b"{}", "0" * 64)
    _assert_error(exc, "POLICY_DIGEST:SHA256_MISMATCH")


def test_policy_atk_05_closed_world_unknown_key() -> None:
    source = load_bundled_draft().documents["CHART_UPSTREAM"]
    mutable = _thaw(source)
    mutable["unexpected"] = True
    raw = json.dumps(mutable, ensure_ascii=False).encode("utf-8")
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_document(raw, _digest(raw), schema_name="chart_of_accounts.v1.schema.json")
    _assert_error(exc, "POLICY_SCHEMA:UNKNOWN_KEY")


def test_policy_atk_06_runtime_object_is_immutable() -> None:
    snapshot = load_bundled_draft()
    with pytest.raises(PolicyLoadError) as exc:
        snapshot.documents["new"] = "forbidden"
    _assert_error(exc, "POLICY_IMMUTABLE:MUTATION_ATTEMPT")
    with pytest.raises(TypeError):
        snapshot.documents._FrozenPolicyMap__data["new"] = "forbidden"


def test_policy_atk_07_reload_after_start() -> None:
    runtime = PolicyRuntime()
    snapshot = load_bundled_draft()
    runtime.initialize(bundled_draft_path(), expected_manifest_sha256=DRAFT_MANIFEST_RAW_SHA256)
    with pytest.raises(PolicyLoadError) as exc:
        runtime.initialize(bundled_draft_path(), expected_manifest_sha256=snapshot.manifest_raw_sha256)
    _assert_error(exc, "POLICY_IMMUTABLE:RELOAD_AFTER_START")


def test_policy_atk_08_unknown_account() -> None:
    with pytest.raises(PolicyLoadError) as exc:
        load_bundled_draft().require_known_account("PL.SGA.INVENTED")
    _assert_error(exc, "ACCOUNT_UNKNOWN:NOT_IN_REGISTRY")


def test_policy_atk_09_forbidden_numeric_code() -> None:
    raw = b'{"code":8215}'
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_document(raw, _digest(raw))
    _assert_error(exc, "ACCOUNT_CODE:FORBIDDEN_INVENTED_CODE")


def test_policy_atk_10_unapproved_overlay_blocks_posting() -> None:
    with pytest.raises(PolicyLoadError) as exc:
        load_bundled_draft().require_postable("PL.SGA.PAYMENT_FEE")
    _assert_error(exc, "POSTING_NOT_ALLOWED:OVERLAY_UNVERIFIED")


def test_activation_is_fail_closed() -> None:
    with pytest.raises(PolicyLoadError) as exc:
        load_bundled_draft().require_activation_allowed()
    _assert_error(exc, "POLICY_APPROVAL:PRODUCT_ACTIVATION_BLOCKED")


def test_bundle_hash_substitution_is_blocked(bundle_copy: Path) -> None:
    path = bundle_copy / "account_mapping_rules.v2.draft.json"
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b"2.1-draft", b"2.1-fraud", 1))
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_bundle(bundle_copy, expected_manifest_sha256=DRAFT_MANIFEST_RAW_SHA256)
    _assert_error(exc, "POLICY_DIGEST:SHA256_MISMATCH")


def test_symlink_artifact_is_blocked(bundle_copy: Path, tmp_path: Path) -> None:
    artifact = bundle_copy / "account_mapping_rules.v2.draft.json"
    external = tmp_path / "external.json"
    external.write_bytes(artifact.read_bytes())
    artifact.unlink()
    artifact.symlink_to(external)
    with pytest.raises(PolicyLoadError) as exc:
        load_policy_bundle(bundle_copy, expected_manifest_sha256=DRAFT_MANIFEST_RAW_SHA256)
    _assert_error(exc, "POLICY_ARTIFACT:MISSING_OR_UNSAFE")


def _thaw(value):
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
