from __future__ import annotations

import hashlib

import pytest

from butler_pc_core.learning_adapters.chat_context_producer import (
    build_chat_context_candidate,
    classify_chat_shadow_label,
    produce_chat_context_candidate,
)
from butler_pc_core.learning_core import UnifiedLearningIntakeGate
from butler_pc_core.learning_core.contracts import stable_json_digest
from butler_pc_core.learning_core.runner import LearningIntakeRunner

_DLP_SEC = "sec" + "ret_detected"


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload() -> dict:
    return {
        "explicit_business_confirmation": True,
        "manager_or_admin_approved": True,
        "shadow_eval_cases": 100,
        "pii_zero": True,
        "false_learning_zero": True,
        "context_digest": _digest("context"),
    }


def _candidate(*, report: bool = True) -> dict:
    data = {
        "schema_version": "integrated_learning_candidate.v1",
        "candidate_id": "ilc-" + "a" * 32,
        "target_kind": "chat_context",
        "adapter_version": "chat_context_producer.v1.13.0",
        "learning_source_type": "verified_chat_context",
        "policy_decision": "allow",
        "verified": True,
        "group_a_verified": True,
        "raw_text_logged": False,
        "external_send_zero": True,
        "model_training": False,
        "peft_training": False,
        "human_review_required": True,
        "auto_apply_to_runtime": False,
        "retention_class": "audit_digest_only",
        "verification": {
            "verified_by": "group_a",
            "verified_at": "2026-07-03T00:00:00Z",
            "evidence_digest": _digest("evidence-report"),
            "evidence_ref": "vault://butler/evidence/GroupA_Report_20260703",
        },
        "source_refs": [{"ref_type": "usage_log", "ref_id_digest": _digest("usage")}],
        "expected_effect_digest": _digest("expected"),
        "payload": _payload(),
    }
    if report:
        data["verification"]["evidence_report_sha256"] = data["verification"]["evidence_digest"]
    data["payload_digest"] = stable_json_digest(data["payload"])
    return data


def _dlp(passed: bool = True, pii: bool = False, sec: bool = False, policy: bool = False) -> dict:
    return {"passed": passed, "pii_detected": pii, _DLP_SEC: sec, "policy_violation": policy}


def _artifact(**overrides) -> dict:
    data = {
        "context_digest": _digest("context"),
        "expected_effect_digest": _digest("expected"),
        "evidence_digest": _digest("evidence-report"),
        "evidence_report_sha256": _digest("evidence-report"),
        "evidence_ref": "vault://butler/evidence/GroupA_Report_20260703",
        "dlp_result": _dlp(),
    }
    data.update(overrides)
    return data


def _evaluate(data: dict, *, run_mode: str = "production"):
    return UnifiedLearningIntakeGate.with_default_adapters(enable_chat=True, chat_run_mode=run_mode).evaluate(data)


def test_production_requires_evidence_report_binding():
    verdict = _evaluate(_candidate(report=False), run_mode="production")
    assert verdict.accepted is False
    assert verdict.drop_reason == "EVIDENCE_REPORT_BINDING_REQUIRED"


def test_integration_requires_evidence_report_binding():
    verdict = _evaluate(_candidate(report=False), run_mode="integration")
    assert verdict.accepted is False
    assert verdict.drop_reason == "EVIDENCE_REPORT_BINDING_REQUIRED"


def test_fixture_test_allows_missing_report_binding():
    assert _evaluate(_candidate(report=False), run_mode="fixture_test").accepted is True


def test_report_binding_must_match_evidence_digest():
    data = _candidate()
    data["verification"]["evidence_report_sha256"] = _digest("other")
    verdict = _evaluate(data)
    assert verdict.accepted is False
    assert verdict.drop_reason == "EVIDENCE_REPORT_BINDING_INVALID"


@pytest.mark.parametrize("value", [None, "", " ", "sha256:not64", True, 1, ["x"]])
def test_report_binding_rejects_invalid_values(value):
    data = _candidate()
    data["verification"]["evidence_report_sha256"] = value
    verdict = _evaluate(data)
    assert verdict.accepted is False
    assert verdict.drop_reason in {"EVIDENCE_REPORT_BINDING_INVALID", "EVIDENCE_REPORT_BINDING_INVALID"}


def test_payload_evidence_report_sha256_is_contamination():
    data = _candidate()
    data["payload"]["evidence_report_sha256"] = data["verification"]["evidence_digest"]
    data["payload_digest"] = stable_json_digest(data["payload"])
    verdict = _evaluate(data)
    assert verdict.accepted is False
    assert verdict.drop_reason == "SCHEMA_KEYS_INVALID"


@pytest.mark.parametrize("field", ["run_mode", "fixture_mode"])
def test_candidate_mode_keys_are_forbidden_anywhere(field):
    data = _candidate()
    data["payload"][field] = "fixture_test"
    data["payload_digest"] = stable_json_digest(data["payload"])
    verdict = _evaluate(data)
    assert verdict.accepted is False
    assert verdict.drop_reason == "FIXTURE_MODE_FORBIDDEN"


def test_unknown_harness_run_mode_fails_closed():
    verdict = _evaluate(_candidate(), run_mode="debug")
    assert verdict.accepted is False
    assert verdict.drop_reason == "RUN_MODE_INVALID"


def test_evidence_digest_context_reuse_remains_blocked():
    data = _candidate()
    data["verification"]["evidence_digest"] = data["payload"]["context_digest"]
    data["verification"]["evidence_report_sha256"] = data["payload"]["context_digest"]
    verdict = _evaluate(data)
    assert verdict.accepted is False
    assert verdict.drop_reason == "EVIDENCE_DIGEST_INVALID"


def test_producer_builds_candidate_with_verification_report_only():
    built = build_chat_context_candidate(_artifact())
    assert built["verification"]["evidence_report_sha256"] == _digest("evidence-report")
    assert "evidence_report_sha256" not in built["payload"]
    assert _evaluate(built).accepted is True


def test_producer_requires_body_dlp_gate_when_gate_input_given():
    built = build_chat_context_candidate(_artifact(), body_gate_input={"dlp_result": _dlp()})
    assert _evaluate(built).accepted is True


def test_producer_drops_when_body_dlp_gate_not_run():
    runner = LearningIntakeRunner.default("/tmp/q", enable_chat=True, chat_run_mode="production")
    result = produce_chat_context_candidate(_artifact(), runner, body_gate_input={})
    assert result["accepted"] is False
    assert result["drop_reason"] == "DLP_NOT_RUN"


@pytest.mark.parametrize(
    ("dlp_result", "expected"),
    [
        (_dlp(), "LEARN"),
        (_dlp(passed=False, pii=True), "BLOCK"),
        (_dlp(passed=False, sec=True), "BLOCK"),
        (_dlp(passed=False, policy=True), "BLOCK"),
    ],
)
def test_shadow_label_dlp_cases(dlp_result, expected):
    assert classify_chat_shadow_label(payload=_payload(), dlp_result=dlp_result) == expected


def test_shadow_label_non_business_is_exclude():
    assert classify_chat_shadow_label(payload=dict(_payload(), explicit_business_confirmation=False), dlp_result=_dlp()) == "EXCLUDE"


def test_shadow_label_unverified_is_drop():
    assert classify_chat_shadow_label(payload=dict(_payload(), shadow_eval_cases=1), dlp_result=_dlp()) == "DROP"


@pytest.mark.parametrize(
    "bad_field",
    ["raw_text", "prompt_text", "response", "user_name", "messenger", "timestamp", "message_id"],
)
def test_raw_identity_fields_remain_blocked(bad_field):
    data = _candidate()
    data[bad_field] = "blocked"
    verdict = _evaluate(data)
    assert verdict.accepted is False
    assert "FORBIDDEN_FIELD" in verdict.drop_reason or "CANDIDATE_UNKNOWN_FIELD" in verdict.drop_reason
