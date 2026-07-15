from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from butler_pc_core.accounting.policy import (
    CHART_RAW_SHA256,
    DRAFT_MANIFEST_RAW_SHA256,
    MAPPING_V1_RAW_SHA256,
    PolicyLoadError,
    bundled_draft_path,
    load_bundled_draft,
    load_policy_bundle,
)


def test_bundled_contract_is_bound_to_raw_source_bytes() -> None:
    root = bundled_draft_path()
    assert hashlib.sha256((root / "policy_bundle_manifest.v2.1.json").read_bytes()).hexdigest() == DRAFT_MANIFEST_RAW_SHA256
    assert hashlib.sha256((root / "upstream/chart_of_accounts.atlink.v1.json").read_bytes()).hexdigest() == CHART_RAW_SHA256
    assert hashlib.sha256((root / "upstream/account_mapping_rules.v1.json").read_bytes()).hexdigest() == MAPPING_V1_RAW_SHA256


def test_all_runtime_schemas_are_valid_draft_2020_12() -> None:
    schema_dir = Path(__file__).parents[3] / "butler_pc_core/accounting/policy/schemas"
    for path in schema_dir.glob("*.schema.json"):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_draft_snapshot_is_complete_but_not_operational() -> None:
    snapshot = load_bundled_draft()
    assert snapshot.profile_id == "atlink.smb.v1"
    assert snapshot.bundle_version == "2.1-draft"
    assert len(snapshot.documents) == 9
    assert len(snapshot.account_ids) == 85
    assert len(snapshot.posting_decisions) == 85
    assert snapshot.journal_auto_post_allowed is False
    assert snapshot.operation_ready is False


def test_repr_never_contains_policy_values() -> None:
    snapshot = load_bundled_draft()
    rendered = repr(snapshot.documents)
    assert "keys=" in rendered
    assert "지급수수료" not in rendered
    assert "에이티링크" not in rendered


def test_nested_unknown_key_is_blocked(rewrite_artifact, bundle_copy: Path) -> None:
    expected = rewrite_artifact(
        bundle_copy,
        "MAPPING_V2_DRAFT",
        lambda document: document["post_mapping_guards"][0].update({"surprise": True}),
    )
    with pytest.raises(PolicyLoadError, match="^POLICY_SCHEMA:UNKNOWN_KEY$"):
        load_policy_bundle(bundle_copy, expected_manifest_sha256=expected)


def test_duplicate_rule_id_is_blocked(rewrite_artifact, bundle_copy: Path) -> None:
    def mutate(document):
        document["rules"][1]["rule_id"] = document["rules"][0]["rule_id"]

    expected = rewrite_artifact(bundle_copy, "MAPPING_V2_DRAFT", mutate)
    with pytest.raises(PolicyLoadError, match="^POLICY_SCHEMA:DUPLICATE_RULE_ID$"):
        load_policy_bundle(bundle_copy, expected_manifest_sha256=expected)


def test_predicate_field_injection_is_blocked(rewrite_artifact, bundle_copy: Path) -> None:
    def mutate(document):
        document["rules"][0]["predicate"]["all"][0]["field"] = "raw_counterparty_name"

    expected = rewrite_artifact(bundle_copy, "MAPPING_V2_DRAFT", mutate)
    with pytest.raises(PolicyLoadError, match="^POLICY_SCHEMA:INVALID_DOCUMENT$"):
        load_policy_bundle(bundle_copy, expected_manifest_sha256=expected)


def test_operator_injection_is_blocked(rewrite_artifact, bundle_copy: Path) -> None:
    def mutate(document):
        document["rules"][0]["predicate"]["all"][0]["op"] = "REGEX"

    expected = rewrite_artifact(bundle_copy, "MAPPING_V2_DRAFT", mutate)
    with pytest.raises(PolicyLoadError, match="^POLICY_SCHEMA:INVALID_DOCUMENT$"):
        load_policy_bundle(bundle_copy, expected_manifest_sha256=expected)


def test_priority_tie_is_blocked(rewrite_artifact, bundle_copy: Path) -> None:
    def mutate(document):
        document["rules"][1]["priority"] = document["rules"][0]["priority"]

    expected = rewrite_artifact(bundle_copy, "MAPPING_V2_DRAFT", mutate)
    with pytest.raises(PolicyLoadError, match="^POLICY_SCHEMA:AMBIGUOUS_RULE_PRIORITY$"):
        load_policy_bundle(bundle_copy, expected_manifest_sha256=expected)


def test_wrong_profile_is_blocked(rewrite_artifact, bundle_copy: Path) -> None:
    expected = rewrite_artifact(
        bundle_copy,
        "MAPPING_V2_DRAFT",
        lambda document: document.update({"policy_profile_id": "other.profile"}),
    )
    with pytest.raises(PolicyLoadError, match="^POLICY_SCHEMA:INVALID_DOCUMENT$"):
        load_policy_bundle(bundle_copy, expected_manifest_sha256=expected)


def test_mixed_bundle_version_is_blocked(rewrite_artifact, bundle_copy: Path) -> None:
    expected = rewrite_artifact(
        bundle_copy,
        "MAPPING_V2_DRAFT",
        lambda document: document.update({"bundle_version": "2.2"}),
    )
    with pytest.raises(PolicyLoadError, match="^POLICY_VERSION:MIXED_BUNDLE_VERSION$"):
        load_policy_bundle(bundle_copy, expected_manifest_sha256=expected)


def test_blocked_bundle_cannot_claim_operation_ready(rewrite_artifact, bundle_copy: Path) -> None:
    def mutate(document):
        document["operation_ready"] = True
        document["journal_auto_post_allowed"] = True

    expected = rewrite_artifact(bundle_copy, "BINDING_STATUS", mutate)
    with pytest.raises(PolicyLoadError, match="^POLICY_APPROVAL:BLOCKED_BUNDLE_CLAIMS_READY$"):
        load_policy_bundle(bundle_copy, expected_manifest_sha256=expected)


def test_approved_manifest_requires_approval_id(bundle_copy: Path) -> None:
    manifest_path = bundle_copy / "policy_bundle_manifest.v2.1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "APPROVED"
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_path.write_bytes(raw)
    with pytest.raises(PolicyLoadError, match="^POLICY_APPROVAL:MISSING$"):
        load_policy_bundle(bundle_copy, expected_manifest_sha256=hashlib.sha256(raw).hexdigest())
