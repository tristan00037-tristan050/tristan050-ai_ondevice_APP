from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from butler_pc_core.learning_adapters.chat_context import ChatContextAdapter
from butler_pc_core.learning_adapters.chat_context_producer import (
    ALLOWED_DROP_REASONS,
    build_chat_context_candidate,
    classify_chat_context_shadow_eval_label,
    ingest_verified_chat_context,
)
from butler_pc_core.learning_core import AdapterRegistry, UnifiedLearningIntakeGate
from butler_pc_core.learning_core.contracts import is_sha256, stable_json_digest
from butler_pc_core.learning_core.queue import ArtifactQueue
from butler_pc_core.learning_core.runner import LearningIntakeRunner


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _runner(queue_path, *, enabled: bool = True):
    registry = AdapterRegistry()
    registry.register(ChatContextAdapter(enabled=enabled))
    return LearningIntakeRunner(UnifiedLearningIntakeGate(registry), ArtifactQueue(queue_path))


def _usage_ref(value: str = "usage"):
    return {"ref_type": "usage_log", "ref_id_digest": _digest(value)}


def _artifact(**overrides):
    data = {
        "explicit_business_confirmation": True,
        "manager_or_admin_approved": True,
        "shadow_eval_cases": 100,
        "pii_zero": True,
        "false_learning_zero": True,
        "context_digest": _digest("context"),
        "expected_effect_digest": _digest("effect"),
        "verified_by": "group_a",
        "verified_at": "2026-07-03T00:00:00Z",
        "evidence_ref": "vault://butler/evidence/groupA_20260703_ok",
        "evidence_digest": _digest("evidence-report"),
        "evidence_report_sha256": _digest("evidence-report"),
        "source_refs": (_usage_ref(),),
    }
    data.update(overrides)
    return data


def _assert_no_queue(path):
    assert not path.exists()


def _read_one_record(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def _drop(overrides, tmp_path, name="queue.jsonl", *, run_mode: str = "production"):
    return ingest_verified_chat_context(_artifact(**overrides), _runner(tmp_path / name), run_mode=run_mode)


def test_verified_chat_context_ingests_when_chat_enabled(tmp_path):
    queue_path = tmp_path / "queue.jsonl"
    result = ingest_verified_chat_context(_artifact(), _runner(queue_path, enabled=True))

    assert result["accepted"] is True
    assert result["queue_appended"] is True
    assert result["candidate_id"].startswith("ilc-")
    assert is_sha256(result["payload_digest"])
    record = _read_one_record(queue_path)
    assert record["target_kind"] == "chat_context"
    assert record["retention_class"] == "audit_digest_only"


def test_verified_chat_context_drops_by_default_when_chat_disabled(tmp_path):
    queue_path = tmp_path / "disabled.jsonl"
    result = ingest_verified_chat_context(_artifact(), _runner(queue_path, enabled=False))

    assert result["accepted"] is False
    assert result["drop_reason"] == "CHAT_CONTEXT_DISABLED"
    assert result["queue_appended"] is False
    _assert_no_queue(queue_path)


def test_shadow_eval_count_below_threshold_drops_without_queue_append(tmp_path):
    queue_path = tmp_path / "shadow.jsonl"
    result = ingest_verified_chat_context(_artifact(shadow_eval_cases=99), _runner(queue_path))

    assert result["accepted"] is False
    assert result["drop_reason"] == "SHADOW_EVAL_CASES_TOO_LOW"
    assert result["queue_appended"] is False
    _assert_no_queue(queue_path)


def test_shadow_eval_count_rejects_string_and_bool_inputs(tmp_path):
    string_result = _drop({"shadow_eval_cases": "100"}, tmp_path, "string.jsonl")
    bool_result = _drop({"shadow_eval_cases": True}, tmp_path, "bool.jsonl")

    assert string_result["accepted"] is False
    assert string_result["drop_reason"] == "SCHEMA_KEYS_INVALID"
    assert bool_result["accepted"] is False
    assert bool_result["drop_reason"] == "SCHEMA_KEYS_INVALID"
    _assert_no_queue(tmp_path / "string.jsonl")
    _assert_no_queue(tmp_path / "bool.jsonl")


def test_boolean_fields_reject_string_values(tmp_path):
    result = _drop({"explicit_business_confirmation": "false"}, tmp_path)

    assert result["accepted"] is False
    assert result["drop_reason"] == "BUSINESS_CONFIRMATION_REQUIRED"
    assert result["queue_appended"] is False
    _assert_no_queue(tmp_path / "queue.jsonl")


def test_required_gate_booleans_must_be_true(tmp_path):
    business = _drop({"explicit_business_confirmation": False}, tmp_path, "business.jsonl")
    approval = _drop({"manager_or_admin_approved": False}, tmp_path, "approval.jsonl")

    assert business["accepted"] is False
    assert business["drop_reason"] == "BUSINESS_CONFIRMATION_REQUIRED"
    assert approval["accepted"] is False
    assert approval["drop_reason"] == "MANAGER_APPROVAL_REQUIRED"
    _assert_no_queue(tmp_path / "business.jsonl")
    _assert_no_queue(tmp_path / "approval.jsonl")


def test_shadow_eval_zero_flags_drop_without_queue_append(tmp_path):
    pii_result = _drop({"pii_zero": False}, tmp_path, "pii.jsonl")
    false_learning_result = _drop({"false_learning_zero": False}, tmp_path, "false_learning.jsonl")

    assert pii_result["accepted"] is False
    assert pii_result["drop_reason"] == "PII_NOT_ZERO"
    assert false_learning_result["accepted"] is False
    assert false_learning_result["drop_reason"] == "FALSE_LEARNING_NOT_ZERO"
    _assert_no_queue(tmp_path / "pii.jsonl")
    _assert_no_queue(tmp_path / "false_learning.jsonl")


def test_context_digest_invalid_drops_before_queue(tmp_path):
    queue_path = tmp_path / "digest.jsonl"
    result = ingest_verified_chat_context(_artifact(context_digest="not-a-digest"), _runner(queue_path))

    assert result["accepted"] is False
    assert result["drop_reason"] == "CONTEXT_DIGEST_INVALID"
    assert result["queue_appended"] is False
    _assert_no_queue(queue_path)


def test_evidence_digest_invalid_drops_before_queue(tmp_path):
    result = _drop({"evidence_digest": "not-a-digest"}, tmp_path)

    assert result["accepted"] is False
    assert result["drop_reason"] == "EVIDENCE_DIGEST_INVALID"
    assert result["queue_appended"] is False
    _assert_no_queue(tmp_path / "queue.jsonl")


def test_evidence_digest_is_required_without_fallback(tmp_path):
    missing = _artifact()
    missing.pop("evidence_digest")
    none_value = _drop({"evidence_digest": None}, tmp_path, "none.jsonl")
    empty_value = _drop({"evidence_digest": ""}, tmp_path, "empty.jsonl")
    blank_value = _drop({"evidence_digest": "   "}, tmp_path, "blank.jsonl")

    missing_result = ingest_verified_chat_context(missing, _runner(tmp_path / "missing.jsonl"))

    assert missing_result["drop_reason"] == "EVIDENCE_DIGEST_INVALID"
    assert none_value["drop_reason"] == "EVIDENCE_DIGEST_INVALID"
    assert empty_value["drop_reason"] == "EVIDENCE_DIGEST_INVALID"
    assert blank_value["drop_reason"] == "EVIDENCE_DIGEST_INVALID"
    _assert_no_queue(tmp_path / "missing.jsonl")
    _assert_no_queue(tmp_path / "none.jsonl")
    _assert_no_queue(tmp_path / "empty.jsonl")
    _assert_no_queue(tmp_path / "blank.jsonl")


def test_evidence_digest_rejects_surrounding_whitespace(tmp_path):
    result = _drop({"evidence_digest": f" {_digest('evidence-report')} "}, tmp_path)

    assert result["accepted"] is False
    assert result["drop_reason"] == "EVIDENCE_DIGEST_INVALID"
    _assert_no_queue(tmp_path / "queue.jsonl")


def test_evidence_digest_matching_context_digest_is_rejected_as_fallback(tmp_path):
    result = _drop({"evidence_digest": _digest("context")}, tmp_path)

    assert result["accepted"] is False
    assert result["drop_reason"] == "EVIDENCE_DIGEST_INVALID"
    _assert_no_queue(tmp_path / "queue.jsonl")


def test_evidence_digest_binds_to_shadow_eval_report_when_provided(tmp_path):
    queue_path = tmp_path / "bound.jsonl"
    evidence_digest = _digest("group-a-shadow-report")
    accepted = ingest_verified_chat_context(
        _artifact(evidence_digest=evidence_digest, evidence_report_sha256=evidence_digest),
        _runner(queue_path),
    )
    mismatched = _drop(
        {
            "evidence_digest": evidence_digest,
            "evidence_report_sha256": _digest("different-shadow-report"),
        },
        tmp_path,
        "mismatch.jsonl",
    )

    assert accepted["accepted"] is True
    assert accepted["queue_appended"] is True
    assert mismatched["accepted"] is False
    assert mismatched["drop_reason"] == "EVIDENCE_REPORT_BINDING_INVALID"
    _assert_no_queue(tmp_path / "mismatch.jsonl")


def test_evidence_report_sha256_is_required_outside_fixture_mode(tmp_path):
    missing = _artifact()
    missing.pop("evidence_report_sha256")

    result = ingest_verified_chat_context(missing, _runner(tmp_path / "missing-report.jsonl"))

    assert result["accepted"] is False
    assert result["drop_reason"] == "EVIDENCE_REPORT_BINDING_REQUIRED"
    assert result["queue_appended"] is False
    _assert_no_queue(tmp_path / "missing-report.jsonl")


def test_fixture_test_mode_allows_missing_evidence_report_binding(tmp_path):
    queue_path = tmp_path / "fixture-report.jsonl"
    fixture = _artifact(evidence_ref="digest-only-fixture")
    fixture.pop("evidence_report_sha256")

    candidate = build_chat_context_candidate(fixture, run_mode="fixture_test")
    result = ingest_verified_chat_context(fixture, _runner(queue_path), run_mode="fixture_test")

    assert "evidence_report_sha256" not in candidate["verification"]
    assert result["accepted"] is True
    assert result["queue_appended"] is True


def test_unknown_run_mode_drops_with_fixed_code(tmp_path):
    result = ingest_verified_chat_context(_artifact(), _runner(tmp_path / "bad-run-mode.jsonl"), run_mode="dry_run")

    assert result["accepted"] is False
    assert result["drop_reason"] == "RUN_MODE_INVALID"
    assert result["queue_appended"] is False
    _assert_no_queue(tmp_path / "bad-run-mode.jsonl")


def test_source_refs_allow_usage_log_and_approval_but_block_other_types(tmp_path):
    queue_path = tmp_path / "allowed.jsonl"
    allowed = ingest_verified_chat_context(
        _artifact(
            source_refs=(
                _usage_ref("usage"),
                {"ref_type": "approval", "ref_id_digest": _digest("approval")},
            )
        ),
        _runner(queue_path),
    )
    blocked = ingest_verified_chat_context(
        _artifact(source_refs=(_usage_ref("usage"), {"ref_type": "folder", "ref_id_digest": _digest("folder")})),
        _runner(tmp_path / "blocked.jsonl"),
    )

    assert allowed["accepted"] is True
    assert blocked["accepted"] is False
    assert blocked["drop_reason"] == "SOURCE_REF_INVALID"
    _assert_no_queue(tmp_path / "blocked.jsonl")


def test_source_refs_require_at_least_one_usage_log_ref(tmp_path):
    result = _drop({"source_refs": ({"ref_type": "approval", "ref_id_digest": _digest("approval-only")},)}, tmp_path)

    assert result["accepted"] is False
    assert result["drop_reason"] == "SOURCE_REF_INVALID"
    _assert_no_queue(tmp_path / "queue.jsonl")


def test_source_refs_malformed_inputs_return_controlled_drops(tmp_path):
    single_object = _drop({"source_refs": {"ref_type": "usage_log", "ref_id_digest": _digest("usage")}}, tmp_path, "single.jsonl")
    non_object_item = _drop({"source_refs": ["not-a-ref"]}, tmp_path, "item.jsonl")

    assert single_object["accepted"] is False
    assert single_object["drop_reason"] == "SOURCE_REF_INVALID"
    assert non_object_item["accepted"] is False
    assert non_object_item["drop_reason"] == "SOURCE_REF_INVALID"
    _assert_no_queue(tmp_path / "single.jsonl")
    _assert_no_queue(tmp_path / "item.jsonl")


def test_raw_material_fields_are_refused_before_runner(tmp_path):
    raw_field_results = [
        ingest_verified_chat_context(_artifact(prompt="secret"), _runner(tmp_path / "prompt.jsonl")),
        ingest_verified_chat_context(_artifact(response_text="answer"), _runner(tmp_path / "response.jsonl")),
        ingest_verified_chat_context(_artifact(user_name="person"), _runner(tmp_path / "user.jsonl")),
        ingest_verified_chat_context(_artifact(timestamp_raw="2026-07-03T00:00:00Z"), _runner(tmp_path / "time.jsonl")),
    ]

    assert [result["accepted"] for result in raw_field_results] == [False, False, False, False]
    assert [result["drop_reason"] for result in raw_field_results] == ["SCHEMA_KEYS_INVALID"] * 4
    for name in ("prompt.jsonl", "response.jsonl", "user.jsonl", "time.jsonl"):
        _assert_no_queue(tmp_path / name)


def test_unknown_artifact_fields_return_code_only_drop_reason(tmp_path):
    raw_key = "/Users/acme/private/chat-log.txt"
    result = ingest_verified_chat_context(
        _artifact(**{raw_key: "do not echo this key"}),
        _runner(tmp_path / "queue.jsonl"),
    )

    assert result["accepted"] is False
    assert result["drop_reason"] == "SCHEMA_KEYS_INVALID"
    assert raw_key not in result["drop_reason"]
    assert result["queue_appended"] is False
    _assert_no_queue(tmp_path / "queue.jsonl")


def test_candidate_envelope_is_digest_only_exact_payload_and_exact_verification():
    candidate = build_chat_context_candidate(_artifact())

    assert candidate["schema_version"] == "integrated_learning_candidate.v1"
    assert candidate["target_kind"] == "chat_context"
    assert candidate["adapter_version"] == "chat_context_producer.v1.0.0"
    assert candidate["learning_source_type"] == "verified_chat_context"
    assert candidate["payload_digest"] == stable_json_digest(candidate["payload"])
    assert set(candidate["payload"]) == {
        "explicit_business_confirmation",
        "manager_or_admin_approved",
        "shadow_eval_cases",
        "pii_zero",
        "false_learning_zero",
        "context_digest",
    }
    assert set(candidate["verification"]) == {
        "verified_by",
        "verified_at",
        "evidence_digest",
        "evidence_ref",
        "evidence_report_sha256",
    }
    assert candidate["verification"]["verified_by"] == "group_a"
    assert candidate["verification"]["verified_at"] == "2026-07-03T00:00:00Z"
    assert candidate["verification"]["evidence_digest"] == _digest("evidence-report")
    assert candidate["verification"]["evidence_report_sha256"] == _digest("evidence-report")
    assert candidate["verification"]["evidence_ref"] == "vault://butler/evidence/groupA_20260703_ok"
    assert candidate["raw_text_logged"] is False
    assert candidate["external_send_zero"] is True
    assert candidate["model_training"] is False
    assert candidate["peft_training"] is False
    assert candidate["human_review_required"] is True
    assert candidate["auto_apply_to_runtime"] is False
    assert candidate["retention_class"] == "audit_digest_only"
    assert candidate["source_refs"] == [_usage_ref()]


def test_chat_context_queue_idempotency_keeps_second_ingest_from_double_append(tmp_path):
    queue_path = tmp_path / "queue.jsonl"
    runner = _runner(queue_path)

    first = ingest_verified_chat_context(_artifact(), runner)
    second = ingest_verified_chat_context(_artifact(), runner)

    assert first["accepted"] is True and first["queue_appended"] is True
    assert second["accepted"] is True and second["queue_appended"] is False
    assert second["queue_reason"] == "IDEMPOTENT_DUPLICATE"
    assert len(queue_path.read_text(encoding="utf-8").splitlines()) == 1


def test_valid_chat_context_accepts_overblock_zero_contract(tmp_path):
    queue_path = tmp_path / "overblock.jsonl"
    result = ingest_verified_chat_context(
        _artifact(
            shadow_eval_cases=127,
            source_refs=(_usage_ref("usage-overblock-zero"), {"ref_type": "approval", "ref_id_digest": _digest("approval")}),
        ),
        _runner(queue_path),
    )

    assert result["accepted"] is True
    assert result["queue_appended"] is True
    record = _read_one_record(queue_path)
    assert record["target_kind"] == "chat_context"


def test_verified_by_rejects_arbitrary_values(tmp_path):
    result = _drop({"verified_by": "alice"}, tmp_path)

    assert result["accepted"] is False
    assert result["drop_reason"] == "VERIFIED_BY_INVALID"
    _assert_no_queue(tmp_path / "queue.jsonl")


def test_verified_by_accepts_only_controlled_roles():
    for role in ("group_a", "integrated_learning_verifier", "privacy_officer", "security_reviewer"):
        candidate = build_chat_context_candidate(_artifact(verified_by=role))
        assert candidate["verification"]["verified_by"] == role


def test_verified_by_roles_survive_unified_gate_ingest(tmp_path):
    for role in ("group_a", "integrated_learning_verifier", "privacy_officer", "security_reviewer"):
        result = ingest_verified_chat_context(
            _artifact(verified_by=role, source_refs=(_usage_ref(role),)),
            _runner(tmp_path / f"{role}.jsonl"),
        )

        assert result["accepted"] is True
        assert result["drop_reason"] is None


def test_published_schema_accepts_chat_binding_field_and_sha256_ref():
    import jsonschema

    schema = json.loads(Path("schemas/learning/integrated_learning_candidate_v1.schema.json").read_text(encoding="utf-8"))
    candidate = build_chat_context_candidate(_artifact(evidence_ref=_digest("evidence-ref")))

    jsonschema.Draft7Validator(schema).validate(candidate)


def test_verified_at_rejects_non_rfc3339_value(tmp_path):
    result = _drop({"verified_at": "2026/07/03 00:00:00"}, tmp_path)

    assert result["accepted"] is False
    assert result["drop_reason"] == "VERIFIED_AT_INVALID"
    _assert_no_queue(tmp_path / "queue.jsonl")


def test_verified_at_rejects_timezone_offset_fraction_and_missing_z(tmp_path):
    offset = _drop({"verified_at": "2026-07-03T09:00:00+09:00"}, tmp_path, "offset.jsonl")
    fraction = _drop({"verified_at": "2026-07-03T00:00:00.000Z"}, tmp_path, "fraction.jsonl")
    missing_z = _drop({"verified_at": "2026-07-03T00:00:00"}, tmp_path, "missing_z.jsonl")

    assert offset["drop_reason"] == "VERIFIED_AT_INVALID"
    assert fraction["drop_reason"] == "VERIFIED_AT_INVALID"
    assert missing_z["drop_reason"] == "VERIFIED_AT_INVALID"
    _assert_no_queue(tmp_path / "offset.jsonl")
    _assert_no_queue(tmp_path / "fraction.jsonl")
    _assert_no_queue(tmp_path / "missing_z.jsonl")


def test_verified_at_rejects_invalid_calendar_date(tmp_path):
    result = _drop({"verified_at": "2026-02-30T00:00:00Z"}, tmp_path)

    assert result["accepted"] is False
    assert result["drop_reason"] == "VERIFIED_AT_INVALID"
    _assert_no_queue(tmp_path / "queue.jsonl")


def test_evidence_ref_rejects_raw_path_and_url_values(tmp_path):
    raw_path = _drop({"evidence_ref": "/Users/acme/private/log.json"}, tmp_path, "path.jsonl")
    http_url = _drop({"evidence_ref": "https://example.com/evidence"}, tmp_path, "url.jsonl")

    assert raw_path["drop_reason"] == "EVIDENCE_REF_INVALID"
    assert http_url["drop_reason"] == "EVIDENCE_REF_INVALID"
    _assert_no_queue(tmp_path / "path.jsonl")
    _assert_no_queue(tmp_path / "url.jsonl")


def test_evidence_ref_rejects_parent_traversal_user_id_and_whitespace(tmp_path):
    parent = _drop({"evidence_ref": "vault://butler/evidence/../secret"}, tmp_path, "parent.jsonl")
    user_id = _drop({"evidence_ref": "vault://butler/evidence/alice@example"}, tmp_path, "user.jsonl")
    spaced = _drop({"evidence_ref": "vault://butler/evidence/chat context"}, tmp_path, "space.jsonl")

    assert parent["drop_reason"] == "EVIDENCE_REF_INVALID"
    assert user_id["drop_reason"] == "EVIDENCE_REF_INVALID"
    assert spaced["drop_reason"] == "EVIDENCE_REF_INVALID"
    _assert_no_queue(tmp_path / "parent.jsonl")
    _assert_no_queue(tmp_path / "user.jsonl")
    _assert_no_queue(tmp_path / "space.jsonl")


def test_evidence_ref_rejects_short_token_and_accepts_minimum_token(tmp_path):
    rejected = ingest_verified_chat_context(
        _artifact(evidence_ref="vault://butler/evidence/short_token_15x"),
        _runner(tmp_path / "short.jsonl"),
    )
    accepted = build_chat_context_candidate(_artifact(evidence_ref="vault://butler/evidence/sixteen_token_ok"))

    assert rejected["accepted"] is False
    assert rejected["drop_reason"] == "EVIDENCE_REF_INVALID"
    assert accepted["verification"]["evidence_ref"] == "vault://butler/evidence/sixteen_token_ok"
    _assert_no_queue(tmp_path / "short.jsonl")


def test_evidence_ref_accepts_sha256_and_butler_secret_refs():
    refs = (
        _digest("evidence-ref"),
        "vault://butler/evidence/groupA_20260703_ok",
        "keyring://butler/evidence/groupA_20260703_ok",
    )

    for ref in refs:
        candidate = build_chat_context_candidate(_artifact(evidence_ref=ref))
        assert candidate["verification"]["evidence_ref"] == ref


def test_digest_only_fixture_requires_fixture_test_run_mode(tmp_path):
    production = _drop({"evidence_ref": "digest-only-fixture"}, tmp_path, "production.jsonl")
    fixture = ingest_verified_chat_context(
        _artifact(evidence_ref="digest-only-fixture"),
        _runner(tmp_path / "fixture.jsonl"),
        run_mode="fixture_test",
    )

    assert production["accepted"] is False
    assert production["drop_reason"] == "EVIDENCE_REF_INVALID"
    assert fixture["accepted"] is True
    assert fixture["queue_appended"] is True
    _assert_no_queue(tmp_path / "production.jsonl")


def test_raw_runtime_mode_keys_are_forbidden_before_runner(tmp_path):
    raw_run_mode = ingest_verified_chat_context(
        _artifact(run_mode="fixture_test"),
        _runner(tmp_path / "raw-run-mode.jsonl"),
    )
    raw_fixture_mode = ingest_verified_chat_context(
        _artifact(fixture_mode=True),
        _runner(tmp_path / "raw-fixture-mode.jsonl"),
    )
    nested_run_mode = ingest_verified_chat_context(
        _artifact(
            source_refs=(
                _usage_ref(),
                {"ref_type": "approval", "ref_id_digest": _digest("approval"), "run_mode": "fixture_test"},
            )
        ),
        _runner(tmp_path / "nested-run-mode.jsonl"),
    )

    assert raw_run_mode["accepted"] is False
    assert raw_run_mode["drop_reason"] == "FIXTURE_MODE_FORBIDDEN"
    assert raw_fixture_mode["accepted"] is False
    assert raw_fixture_mode["drop_reason"] == "FIXTURE_MODE_FORBIDDEN"
    assert nested_run_mode["accepted"] is False
    assert nested_run_mode["drop_reason"] == "FIXTURE_MODE_FORBIDDEN"
    _assert_no_queue(tmp_path / "raw-run-mode.jsonl")
    _assert_no_queue(tmp_path / "raw-fixture-mode.jsonl")
    _assert_no_queue(tmp_path / "nested-run-mode.jsonl")


def test_payload_pollution_with_evidence_report_sha256_is_rejected(tmp_path):
    result = ingest_verified_chat_context(
        _artifact(payload={"evidence_report_sha256": _digest("evidence-report")}),
        _runner(tmp_path / "payload-pollution.jsonl"),
    )

    assert result["accepted"] is False
    assert result["drop_reason"] == "SCHEMA_KEYS_INVALID"
    assert result["queue_appended"] is False
    _assert_no_queue(tmp_path / "payload-pollution.jsonl")


def test_provenance_fields_are_required_without_default_injection(tmp_path):
    missing_verified_by = _artifact()
    missing_verified_by.pop("verified_by")
    missing_verified_at = _artifact()
    missing_verified_at.pop("verified_at")
    missing_evidence_ref = _artifact()
    missing_evidence_ref.pop("evidence_ref")

    results = [
        ingest_verified_chat_context(missing_verified_by, _runner(tmp_path / "by.jsonl")),
        ingest_verified_chat_context(missing_verified_at, _runner(tmp_path / "at.jsonl")),
        ingest_verified_chat_context(missing_evidence_ref, _runner(tmp_path / "ref.jsonl")),
    ]

    assert [result["drop_reason"] for result in results] == [
        "VERIFIED_BY_INVALID",
        "VERIFIED_AT_INVALID",
        "EVIDENCE_REF_INVALID",
    ]
    _assert_no_queue(tmp_path / "by.jsonl")
    _assert_no_queue(tmp_path / "at.jsonl")
    _assert_no_queue(tmp_path / "ref.jsonl")


def test_plain_string_provenance_rejects_strip_drift(tmp_path):
    verified_by = _drop({"verified_by": " group_a"}, tmp_path, "by.jsonl")
    verified_at = _drop({"verified_at": "2026-07-03T00:00:00Z "}, tmp_path, "at.jsonl")
    evidence_ref = _drop({"evidence_ref": " digest-only-fixture"}, tmp_path, "ref.jsonl")

    assert verified_by["drop_reason"] == "VERIFIED_BY_INVALID"
    assert verified_at["drop_reason"] == "VERIFIED_AT_INVALID"
    assert evidence_ref["drop_reason"] == "EVIDENCE_REF_INVALID"
    _assert_no_queue(tmp_path / "by.jsonl")
    _assert_no_queue(tmp_path / "at.jsonl")
    _assert_no_queue(tmp_path / "ref.jsonl")


def test_drop_reasons_are_limited_to_fixed_enum(tmp_path):
    cases = [
        _drop({"verified_by": "alice"}, tmp_path, "by.jsonl"),
        _drop({"verified_at": "2026-07-03T00:00:00"}, tmp_path, "at.jsonl"),
        _drop({"evidence_ref": "file:///tmp/evidence"}, tmp_path, "ref.jsonl"),
        _drop({"evidence_digest": _digest("context")}, tmp_path, "evidence.jsonl"),
        _drop({"evidence_report_sha256": _digest("mismatch")}, tmp_path, "binding.jsonl"),
        _drop({"source_refs": ()}, tmp_path, "source.jsonl"),
        _drop({"context_digest": "bad"}, tmp_path, "context.jsonl"),
    ]

    for result in cases:
        assert result["drop_reason"] in ALLOWED_DROP_REASONS
        assert ":" not in result["drop_reason"]
        assert "{" not in result["drop_reason"]


def test_shadow_eval_label_uses_gate_and_dlp_inputs_without_persisting_label():
    clean_dlp = {
        "passed": True,
        "pii_detected": False,
        "secret_detected": False,
        "policy_violation": False,
    }
    pii_dlp = dict(clean_dlp, passed=False, pii_detected=True)

    assert (
        classify_chat_context_shadow_eval_label(
            dlp_result=clean_dlp,
            explicit_business_confirmation=True,
            manager_or_admin_approved=True,
            pii_zero=True,
            false_learning_zero=True,
        )
        == "LEARN"
    )
    assert (
        classify_chat_context_shadow_eval_label(
            dlp_result=clean_dlp,
            explicit_business_confirmation=False,
            manager_or_admin_approved=True,
            pii_zero=True,
            false_learning_zero=True,
        )
        == "EXCLUDE"
    )
    assert (
        classify_chat_context_shadow_eval_label(
            dlp_result=pii_dlp,
            explicit_business_confirmation=True,
            manager_or_admin_approved=True,
            pii_zero=True,
            false_learning_zero=True,
        )
        == "BLOCK"
    )
    assert (
        classify_chat_context_shadow_eval_label(
            dlp_result=None,
            explicit_business_confirmation=True,
            manager_or_admin_approved=True,
            pii_zero=True,
            false_learning_zero=True,
        )
        == "DROP"
    )
    candidate = build_chat_context_candidate(_artifact())
    assert "shadow_eval_label" not in candidate
    assert "shadow_eval_label" not in candidate["payload"]


def test_static_verifier_rejects_evidence_digest_fallback_pattern(tmp_path):
    repo = tmp_path / "repo"
    producer_path = repo / "butler_pc_core" / "learning_adapters" / "chat_context_producer.py"
    common_path = repo / "butler_pc_core" / "learning_adapters" / "producer_common.py"
    script_path = repo / "scripts" / "verify_integrated_learning_chat_context_producer.py"
    producer_path.parent.mkdir(parents=True)
    common_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.parent.mkdir(parents=True)

    producer_text = Path("butler_pc_core/learning_adapters/chat_context_producer.py").read_text(encoding="utf-8")
    producer_text = producer_text.replace(
        "evidence_digest = _require_evidence_digest(item.evidence_digest, context_digest=context_digest)",
        "evidence_digest = validate_digest_or_drop(item.evidence_digest or context_digest, \"EVIDENCE\")",
    )
    producer_path.write_text(producer_text, encoding="utf-8")
    common_path.write_text(Path("butler_pc_core/learning_adapters/producer_common.py").read_text(encoding="utf-8"), encoding="utf-8")
    script_path.write_text(Path("scripts/verify_integrated_learning_chat_context_producer.py").read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script_path), str(repo)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "CHAT_CONTEXT_PRODUCER_CONTRACT_OK=0" in result.stdout
    assert "ERROR_CODE=CONTRACT_STATIC_VERIFIER_FAIL" in result.stdout


def test_static_verifier_rejects_unconditional_missing_report_pass(tmp_path):
    repo = tmp_path / "repo"
    producer_path = repo / "butler_pc_core" / "learning_adapters" / "chat_context_producer.py"
    common_path = repo / "butler_pc_core" / "learning_adapters" / "producer_common.py"
    script_path = repo / "scripts" / "verify_integrated_learning_chat_context_producer.py"
    contract_path = repo / "butler_pc_core" / "learning_core" / "contracts.py"
    producer_path.parent.mkdir(parents=True)
    common_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.parent.mkdir(parents=True)

    producer_text = Path("butler_pc_core/learning_adapters/chat_context_producer.py").read_text(encoding="utf-8")
    producer_text = producer_text.replace(
        'if raw_value is None:\n        if run_mode == "fixture_test":\n            return None\n        _fail("EVIDENCE_REPORT_BINDING_REQUIRED")',
        "if raw_value is None:\n        return None",
    )
    producer_path.write_text(producer_text, encoding="utf-8")
    common_path.write_text(Path("butler_pc_core/learning_adapters/producer_common.py").read_text(encoding="utf-8"), encoding="utf-8")
    contract_path.write_text(Path("butler_pc_core/learning_core/contracts.py").read_text(encoding="utf-8"), encoding="utf-8")
    script_path.write_text(Path("scripts/verify_integrated_learning_chat_context_producer.py").read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script_path), str(repo)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "CHAT_CONTEXT_PRODUCER_CONTRACT_OK=0" in result.stdout
    assert "ERROR_CODE=EVIDENCE_REPORT_BINDING_REQUIRED_BYPASS" in result.stdout


def test_static_verifier_rejects_runtime_mode_artifact_fields(tmp_path):
    repo = tmp_path / "repo"
    producer_path = repo / "butler_pc_core" / "learning_adapters" / "chat_context_producer.py"
    common_path = repo / "butler_pc_core" / "learning_adapters" / "producer_common.py"
    script_path = repo / "scripts" / "verify_integrated_learning_chat_context_producer.py"
    contract_path = repo / "butler_pc_core" / "learning_core" / "contracts.py"
    producer_path.parent.mkdir(parents=True)
    common_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.parent.mkdir(parents=True)

    producer_text = Path("butler_pc_core/learning_adapters/chat_context_producer.py").read_text(encoding="utf-8")
    producer_text = producer_text.replace(
        "    evidence_report_sha256: str | None = None",
        "    evidence_report_sha256: str | None = None\n    fixture_mode: bool = False",
    )
    producer_path.write_text(producer_text, encoding="utf-8")
    common_path.write_text(Path("butler_pc_core/learning_adapters/producer_common.py").read_text(encoding="utf-8"), encoding="utf-8")
    contract_path.write_text(Path("butler_pc_core/learning_core/contracts.py").read_text(encoding="utf-8"), encoding="utf-8")
    script_path.write_text(Path("scripts/verify_integrated_learning_chat_context_producer.py").read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script_path), str(repo)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "CHAT_CONTEXT_PRODUCER_CONTRACT_OK=0" in result.stdout
    assert "ERROR_CODE=RUNTIME_MODE_ARTIFACT_FIELD_FORBIDDEN" in result.stdout
