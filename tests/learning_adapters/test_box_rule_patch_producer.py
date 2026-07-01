from __future__ import annotations

import json

from butler_pc_core.learning_adapters.box_rule_patch import BoxRulePatchAdapter
from butler_pc_core.learning_adapters.box_rule_patch_producer import (
    Box5RulePatchArtifact,
    box5_artifact_from_verified_rule_base_candidate,
    build_box_rule_patch_candidate,
    ingest_verified_box5_rule_patch,
)
from butler_pc_core.learning_core import AdapterRegistry, UnifiedLearningIntakeGate
from butler_pc_core.learning_core.queue import ArtifactQueue
from butler_pc_core.learning_core.runner import LearningIntakeRunner
from butler_pc_core.learning_core.contracts import is_sha256, stable_json_digest


def _digest(name: str) -> str:
    return "sha256:" + (name.encode("utf-8").hex()[:64]).ljust(64, "0")


def _runner(queue_path):
    registry = AdapterRegistry()
    registry.register(BoxRulePatchAdapter())
    return LearningIntakeRunner(UnifiedLearningIntakeGate(registry), ArtifactQueue(queue_path))


def _artifact(**overrides):
    data = {
        "rule_target": "box5_self_transfer_guard",
        "changed_files": (
            "butler_pc_core/company_profile/matcher.py",
            "tests/accounting/test_self_transfer_guard.py",
            "butler_pc_core/accounting/rulebase_learning/rule_tokens.json",
        ),
        "tests_to_run": ("python3 -m pytest tests/accounting/test_self_transfer_guard.py -q",),
        "expected_current_digest": _digest("matcher-current"),
        "rule_tokens_digest": _digest("rule-tokens"),
        "fixed_eval_report_digest": _digest("group-a-report"),
        "expected_effect_digest": _digest("expected-effect"),
    }
    data.update(overrides)
    return Box5RulePatchArtifact(**data)


def test_verified_box5_artifact_ingests_via_runner_and_queue(tmp_path):
    result = ingest_verified_box5_rule_patch(_artifact(), _runner(tmp_path / "queue.jsonl"))

    assert result["accepted"] is True
    assert result["queue_appended"] is True
    assert result["record_digest"] and is_sha256(result["record_digest"])
    assert result["candidate_id"].startswith("ilc-")

    queue_text = (tmp_path / "queue.jsonl").read_text(encoding="utf-8")
    assert "vault://" not in queue_text
    assert "raw_memo" not in queue_text
    assert "transaction_text" not in queue_text
    assert "account_number_plain" not in queue_text
    assert "prompt" not in queue_text
    record = json.loads(queue_text)
    assert record["target_kind"] == "box_rule_patch"
    assert record["human_review_required"] is True
    assert record["auto_apply_to_runtime"] is False


def test_candidate_builder_outputs_integrated_contract_not_vrb():
    candidate = build_box_rule_patch_candidate(_artifact())

    assert candidate["schema_version"] == "integrated_learning_candidate.v1"
    assert candidate["candidate_id"].startswith("ilc-")
    assert not candidate["candidate_id"].startswith("vrb-")
    assert candidate["learning_source_type"] == "verified_box_rule_patch"
    assert candidate["payload_digest"] == stable_json_digest(candidate["payload"])
    assert "integration_mode" not in candidate
    assert candidate["verification"]["evidence_ref"] == "digest-only-fixture"


def test_unverified_group_a_report_drops_before_queue(tmp_path):
    result = ingest_verified_box5_rule_patch(
        _artifact(group_a_fixed_eval_passed=False),
        _runner(tmp_path / "queue.jsonl"),
    )

    assert result["accepted"] is False
    assert result["drop_reason"] == "GROUP_A_FIXED_EVAL_NOT_PASSED"
    assert result["queue_appended"] is False
    assert not (tmp_path / "queue.jsonl").exists() or not (tmp_path / "queue.jsonl").read_text(encoding="utf-8")


def test_rule_token_config_filename_mismatch_is_locked_as_diff_file_not_allowed(tmp_path):
    result = ingest_verified_box5_rule_patch(
        _artifact(changed_files=("butler_pc_core/accounting/rulebase_learning/rule_token_config.json",)),
        _runner(tmp_path / "queue.jsonl"),
    )

    assert result["accepted"] is False
    assert result["drop_reason"] == "DIFF_FILE_NOT_ALLOWED"
    assert result["queue_appended"] is False


def test_runtime_hotpatch_true_is_blocked(tmp_path):
    result = ingest_verified_box5_rule_patch(
        _artifact(runtime_hotpatch=True),
        _runner(tmp_path / "queue.jsonl"),
    )

    assert result["accepted"] is False
    assert result["drop_reason"] == "RUNTIME_HOTPATCH_FORBIDDEN"
    assert result["queue_appended"] is False


def test_raw_material_mapping_is_rejected_before_runner(tmp_path):
    artifact = {
        "rule_target": "box5_self_transfer_guard",
        "changed_files": ["butler_pc_core/company_profile/matcher.py"],
        "tests_to_run": ["python3 -m pytest tests/accounting/test_self_transfer_guard.py -q"],
        "expected_current_digest": _digest("matcher-current"),
        "rule_tokens_digest": _digest("rule-tokens"),
        "fixed_eval_report_digest": _digest("group-a-report"),
        "expected_effect_digest": _digest("expected-effect"),
        "raw_memo": "사내 자금이동",
    }
    result = ingest_verified_box5_rule_patch(artifact, _runner(tmp_path / "queue.jsonl"))

    assert result["accepted"] is False
    assert "FORBIDDEN_FIELD" in result["drop_reason"]
    assert result["queue_appended"] is False
    assert not (tmp_path / "queue.jsonl").exists()


def test_integration_mode_injection_never_reaches_queue(tmp_path):
    artifact = {
        "rule_target": "box5_self_transfer_guard",
        "changed_files": ["butler_pc_core/company_profile/matcher.py"],
        "tests_to_run": ["python3 -m pytest tests/accounting/test_self_transfer_guard.py -q"],
        "expected_current_digest": _digest("matcher-current"),
        "rule_tokens_digest": _digest("rule-tokens"),
        "fixed_eval_report_digest": _digest("group-a-report"),
        "expected_effect_digest": _digest("expected-effect"),
        "integration_mode": "real",
    }
    result = ingest_verified_box5_rule_patch(artifact, _runner(tmp_path / "queue.jsonl"))

    assert result["accepted"] is False
    assert "INTEGRATION_MODE" in result["drop_reason"] or "FORBIDDEN_FIELD" in result["drop_reason"]
    assert result["queue_appended"] is False


def test_vrb_candidate_is_repackaged_to_ilc_candidate_and_vrb_id_is_not_reused():
    vrb = {
        "schema_version": "verified_rule_base_candidate.v1",
        "candidate_id": "vrb-1234567890abcdef",
        "candidate_kind": "deterministic_rule_patch",
        "target": "box5_self_transfer_guard",
        "group_a_verified": True,
        "approved_rule_token_digest": _digest("approved-rule-token"),
        "group_a_report_digest": _digest("group-a-report"),
        "expected_effect_digest": _digest("expected-effect"),
        "source_usage_log_ids": ["usage-log-1"],
    }
    artifact = box5_artifact_from_verified_rule_base_candidate(
        vrb,
        changed_files=["butler_pc_core/company_profile/matcher.py"],
        tests_to_run=["python3 -m pytest tests/accounting/test_self_transfer_guard.py -q"],
        expected_current_digest=_digest("matcher-current"),
        rule_tokens_digest=_digest("rule-tokens"),
    )
    candidate = build_box_rule_patch_candidate(artifact)

    assert candidate["candidate_id"].startswith("ilc-")
    assert "vrb-1234567890abcdef" not in json.dumps(candidate, ensure_ascii=False)
    assert candidate["source_refs"][0]["ref_type"] == "usage_log"
    assert is_sha256(candidate["source_refs"][0]["ref_id_digest"])


def test_malformed_rule_token_digest_is_fail_closed(tmp_path):
    result = ingest_verified_box5_rule_patch(
        _artifact(rule_tokens_digest="not-a-digest"),
        _runner(tmp_path / "queue.jsonl"),
    )

    assert result["accepted"] is False
    assert result["drop_reason"] == "RULE_TOKENS_DIGEST_INVALID"
    assert result["queue_appended"] is False


def test_queue_idempotency_keeps_second_ingest_from_double_append(tmp_path):
    queue_path = tmp_path / "queue.jsonl"
    runner = _runner(queue_path)
    first = ingest_verified_box5_rule_patch(_artifact(), runner)
    second = ingest_verified_box5_rule_patch(_artifact(), runner)

    assert first["accepted"] is True and first["queue_appended"] is True
    assert second["accepted"] is True and second["queue_appended"] is False
    assert second["queue_reason"] == "IDEMPOTENT_DUPLICATE"
    assert len(queue_path.read_text(encoding="utf-8").splitlines()) == 1
