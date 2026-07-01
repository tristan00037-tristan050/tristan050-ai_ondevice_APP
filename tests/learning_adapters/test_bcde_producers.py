from __future__ import annotations

import hashlib
import json

from butler_pc_core.learning_adapters.approved_fact import ApprovedFactAdapter
from butler_pc_core.learning_adapters.approved_fact_producer import (
    build_approved_fact_candidate,
    ingest_verified_approved_fact,
)
from butler_pc_core.learning_adapters.company_format import CompanyFormatAdapter
from butler_pc_core.learning_adapters.company_format_producer import (
    build_company_format_candidate,
    ingest_verified_company_format,
)
from butler_pc_core.learning_adapters.folder_doc import FolderDocAdapter
from butler_pc_core.learning_adapters.folder_doc_producer import (
    build_folder_doc_candidate,
    ingest_verified_folder_doc,
)
from butler_pc_core.learning_adapters.policy_rule import PolicyRuleAdapter
from butler_pc_core.learning_adapters.policy_rule_producer import (
    build_policy_rule_candidate,
    ingest_verified_policy_rule,
)
from butler_pc_core.learning_core import AdapterRegistry, UnifiedLearningIntakeGate
from butler_pc_core.learning_core.contracts import is_sha256, stable_json_digest
from butler_pc_core.learning_core.queue import ArtifactQueue
from butler_pc_core.learning_core.runner import LearningIntakeRunner


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _runner(adapter, queue_path):
    registry = AdapterRegistry()
    registry.register(adapter)
    return LearningIntakeRunner(UnifiedLearningIntakeGate(registry), ArtifactQueue(queue_path))


def _policy(**overrides):
    data = {
        "policy_status": "ACTIVE",
        "active_policy_digest": _digest("active-policy"),
        "expected_effect_digest": _digest("policy-effect"),
    }
    data.update(overrides)
    return data


def _format(**overrides):
    data = {
        "format_ref": "vault://formats/invoice-v1",
        "template_digest": _digest("template"),
        "format_status": "ACTIVE",
        "expected_effect_digest": _digest("format-effect"),
    }
    data.update(overrides)
    return data


def _fact(**overrides):
    data = {
        "fact_status": "ACTIVE",
        "fact_digest": _digest("fact"),
        "expected_effect_digest": _digest("fact-effect"),
    }
    data.update(overrides)
    return data


def _folder(**overrides):
    data = {
        "folder_ingest_approved": True,
        "traversal_pruned": True,
        "max_depth": 4,
        "max_files": 100,
        "extension": ".PDF",
        "chunk_digest": _digest("chunk"),
        "previous_manifest_digest": _digest("previous"),
        "expected_effect_digest": _digest("folder-effect"),
    }
    data.update(overrides)
    return data


def _assert_queue_record(queue_path, target_kind):
    lines = queue_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["target_kind"] == target_kind
    assert is_sha256(record["record_digest"])
    queue_text = queue_path.read_text(encoding="utf-8")
    for forbidden in (
        "raw_memo",
        "policy_text",
        "template_body",
        "fact_text",
        "folder_content",
        "file_path",
        "local_path",
        "prompt",
        "response_text",
        "account_number_plain",
    ):
        assert forbidden not in queue_text
    return record


def test_policy_rule_verified_artifact_ingests_via_runner_and_queue(tmp_path):
    result = ingest_verified_policy_rule(_policy(), _runner(PolicyRuleAdapter(), tmp_path / "queue.jsonl"))

    assert result["accepted"] is True
    assert result["queue_appended"] is True
    assert result["candidate_id"].startswith("ilc-")
    assert is_sha256(result["payload_digest"])
    _assert_queue_record(tmp_path / "queue.jsonl", "policy_rule")


def test_company_format_verified_artifact_ingests_via_runner_and_queue(tmp_path):
    result = ingest_verified_company_format(_format(), _runner(CompanyFormatAdapter(), tmp_path / "queue.jsonl"))

    assert result["accepted"] is True
    assert result["queue_appended"] is True
    assert result["candidate_id"].startswith("ilc-")
    _assert_queue_record(tmp_path / "queue.jsonl", "company_format")


def test_approved_fact_verified_artifact_ingests_via_runner_and_queue(tmp_path):
    result = ingest_verified_approved_fact(_fact(), _runner(ApprovedFactAdapter(), tmp_path / "queue.jsonl"))

    assert result["accepted"] is True
    assert result["queue_appended"] is True
    assert result["candidate_id"].startswith("ilc-")
    _assert_queue_record(tmp_path / "queue.jsonl", "approved_fact")


def test_folder_doc_verified_artifact_ingests_via_runner_and_queue(tmp_path):
    result = ingest_verified_folder_doc(_folder(), _runner(FolderDocAdapter(), tmp_path / "queue.jsonl"))

    assert result["accepted"] is True
    assert result["queue_appended"] is True
    assert result["candidate_id"].startswith("ilc-")
    _assert_queue_record(tmp_path / "queue.jsonl", "folder_doc")


def test_candidate_builders_match_integrated_contract_source_types_and_payload_digests():
    cases = [
        (build_policy_rule_candidate(_policy()), "policy_rule", "verified_policy_rule"),
        (build_company_format_candidate(_format()), "company_format", "verified_company_format"),
        (build_approved_fact_candidate(_fact()), "approved_fact", "verified_approved_fact"),
        (build_folder_doc_candidate(_folder()), "folder_doc", "verified_folder_doc"),
    ]

    for candidate, target_kind, source_type in cases:
        assert candidate["schema_version"] == "integrated_learning_candidate.v1"
        assert candidate["target_kind"] == target_kind
        assert candidate["learning_source_type"] == source_type
        assert candidate["adapter_version"].endswith("_producer.v1.0.0")
        assert candidate["payload_digest"] == stable_json_digest(candidate["payload"])
        assert candidate["verification"]["evidence_ref"] == "digest-only-fixture"
        assert "integration_mode" not in candidate
        assert all(is_sha256(ref["ref_id_digest"]) for ref in candidate["source_refs"])


def test_policy_negative_cases_drop_without_queue_append(tmp_path):
    inactive = ingest_verified_policy_rule(
        _policy(policy_status="DEPRECATED"),
        _runner(PolicyRuleAdapter(), tmp_path / "inactive.jsonl"),
    )
    deny = ingest_verified_policy_rule(
        _policy(deny_to_allow_auto=True),
        _runner(PolicyRuleAdapter(), tmp_path / "deny.jsonl"),
    )
    string_bool = ingest_verified_policy_rule(
        _policy(deny_to_allow_auto="false"),
        _runner(PolicyRuleAdapter(), tmp_path / "string.jsonl"),
    )

    assert inactive["accepted"] is False
    assert inactive["drop_reason"] == "POLICY_NOT_ACTIVE"
    assert deny["accepted"] is False
    assert deny["drop_reason"] == "DENY_TO_ALLOW_AUTO_FORBIDDEN"
    assert string_bool["accepted"] is False
    assert string_bool["drop_reason"] == "DENY_TO_ALLOW_AUTO_INVALID"
    assert not (tmp_path / "inactive.jsonl").exists()
    assert not (tmp_path / "deny.jsonl").exists()
    assert not (tmp_path / "string.jsonl").exists()


def test_company_format_negative_cases_drop_without_queue_append(tmp_path):
    bad_ref = ingest_verified_company_format(
        _format(format_ref="/Users/example/template.docx"),
        _runner(CompanyFormatAdapter(), tmp_path / "ref.jsonl"),
    )
    inactive = ingest_verified_company_format(
        _format(format_status="DRAFT"),
        _runner(CompanyFormatAdapter(), tmp_path / "status.jsonl"),
    )

    assert bad_ref["accepted"] is False
    assert bad_ref["drop_reason"] == "FORMAT_REF_INVALID"
    assert inactive["accepted"] is False
    assert inactive["drop_reason"] == "FORMAT_NOT_APPROVED"
    assert not (tmp_path / "ref.jsonl").exists()
    assert not (tmp_path / "status.jsonl").exists()


def test_approved_fact_negative_cases_drop_without_queue_append(tmp_path):
    known_bad = ingest_verified_approved_fact(
        _fact(known_bad=True),
        _runner(ApprovedFactAdapter(), tmp_path / "known_bad.jsonl"),
    )
    string_bool = ingest_verified_approved_fact(
        _fact(deprecated="false"),
        _runner(ApprovedFactAdapter(), tmp_path / "string.jsonl"),
    )

    assert known_bad["accepted"] is False
    assert known_bad["drop_reason"] == "FACT_KNOWN_BAD_OR_DEPRECATED"
    assert string_bool["accepted"] is False
    assert string_bool["drop_reason"] == "DEPRECATED_INVALID"
    assert not (tmp_path / "known_bad.jsonl").exists()
    assert not (tmp_path / "string.jsonl").exists()


def test_folder_doc_negative_cases_drop_without_queue_append(tmp_path):
    too_deep = ingest_verified_folder_doc(
        _folder(max_depth=6),
        _runner(FolderDocAdapter(), tmp_path / "depth.jsonl"),
    )
    string_limit = ingest_verified_folder_doc(
        _folder(max_files="500"),
        _runner(FolderDocAdapter(), tmp_path / "string_limit.jsonl"),
    )
    string_bool = ingest_verified_folder_doc(
        _folder(folder_ingest_approved="true"),
        _runner(FolderDocAdapter(), tmp_path / "string_bool.jsonl"),
    )
    bad_extension = ingest_verified_folder_doc(
        _folder(extension=".exe"),
        _runner(FolderDocAdapter(), tmp_path / "ext.jsonl"),
    )

    assert too_deep["accepted"] is False
    assert too_deep["drop_reason"] == "TRAVERSAL_LIMIT_INVALID"
    assert string_limit["accepted"] is False
    assert string_limit["drop_reason"] == "MAX_FILES_INVALID"
    assert string_bool["accepted"] is False
    assert string_bool["drop_reason"] == "FOLDER_INGEST_APPROVED_INVALID"
    assert bad_extension["accepted"] is False
    assert bad_extension["drop_reason"] == "EXTENSION_NOT_ALLOWED"
    assert not (tmp_path / "depth.jsonl").exists()
    assert not (tmp_path / "string_limit.jsonl").exists()
    assert not (tmp_path / "string_bool.jsonl").exists()
    assert not (tmp_path / "ext.jsonl").exists()


def test_source_refs_malformed_inputs_return_controlled_drops(tmp_path):
    single_object = ingest_verified_policy_rule(
        _policy(source_refs={"ref_type": "policy", "ref_id_digest": _digest("policy-ref")}),
        _runner(PolicyRuleAdapter(), tmp_path / "single.jsonl"),
    )
    non_object_item = ingest_verified_policy_rule(
        _policy(source_refs=["not-a-ref"]),
        _runner(PolicyRuleAdapter(), tmp_path / "item.jsonl"),
    )

    assert single_object["accepted"] is False
    assert single_object["drop_reason"] == "SOURCE_REFS_NOT_SEQUENCE"
    assert non_object_item["accepted"] is False
    assert non_object_item["drop_reason"] == "SOURCE_REF_NOT_OBJECT"
    assert not (tmp_path / "single.jsonl").exists()
    assert not (tmp_path / "item.jsonl").exists()


def test_raw_material_fields_drop_before_runner(tmp_path):
    result = ingest_verified_policy_rule(
        _policy(policy_text="allow all"),
        _runner(PolicyRuleAdapter(), tmp_path / "queue.jsonl"),
    )

    assert result["accepted"] is False
    assert "FORBIDDEN_FIELD" in result["drop_reason"]
    assert result["queue_appended"] is False
    assert not (tmp_path / "queue.jsonl").exists()


def test_policy_queue_idempotency_keeps_second_ingest_from_double_append(tmp_path):
    queue_path = tmp_path / "queue.jsonl"
    runner = _runner(PolicyRuleAdapter(), queue_path)

    first = ingest_verified_policy_rule(_policy(), runner)
    second = ingest_verified_policy_rule(_policy(), runner)

    assert first["accepted"] is True and first["queue_appended"] is True
    assert second["accepted"] is True and second["queue_appended"] is False
    assert second["queue_reason"] == "IDEMPOTENT_DUPLICATE"
    assert len(queue_path.read_text(encoding="utf-8").splitlines()) == 1
