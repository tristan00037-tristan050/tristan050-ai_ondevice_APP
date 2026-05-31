from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone

import pytest
from jsonschema.exceptions import ValidationError

from butler_pc_core.connect_loop.learning_candidate_gate import (
    ApprovedRefBundle,
    approve_learning_event,
    build_learning_gate_input,
    create_learning_event_result,
    reject_learning_event,
    select_learning_candidates,
)
from butler_pc_core.connect_loop.learning_event_schema import validate_learning_event
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore

NOW = datetime(2026, 5, 31, tzinfo=timezone.utc)


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def usage_log(**overrides):
    base = {
        "log_id": "ulog-pr-e-001",
        "timestamp": "2026-05-31T00:00:00Z",
        "request_id": "req-pr-e-001",
        "device_id_digest": digest("device"),
        "tenant_id_digest": digest("tenant"),
        "department_id_digest": digest("department"),
        "request_digest": digest("request"),
        "intent_label": "memory_search",
        "box_id": "helper1",
        "endpoint": "POST /v1/helpers/1/search",
        "routing_confidence": 0.93,
        "integration_mode": "real",
        "real_validation_done": True,
        "result_digest": digest("result"),
        "source_digests": [digest("source")],
        "policy_decision": "allow",
        "policy_reason_code": "OK",
        "latency_ms": 12.5,
        "external_send_zero": True,
        "raw_text_logged": False,
        "learning_candidate": True,
        "learning_event_created": False,
        "retention_class": "audit_digest_only",
        "created_by_component": "connect_loop.usage_accumulator",
        "schema_hash": digest("usage_log_schema"),
        "schema_version": "usage_log.v1.1",
    }
    base.update(overrides)
    return base


def envelope(**overrides):
    base = {
        "learning_allowed": True,
        "tenant_scope": "device",
        "retention_days": 30,
        "expires_at": "2026-12-31T00:00:00Z",
        "reason_code": "LEARNING_ALLOWED_SANITIZED",
    }
    base.update(overrides)
    return base


def approved_bundle(**overrides):
    base = {
        "approved_text_ref": "vault://learning-events/pr-e-001",
        "approved_text_digest": digest("approved sanitized text"),
        "sanitized_summary_digest": digest("summary"),
        "runtime_text_for_dlp": "정제된 업무 지식 요약",
    }
    base.update(overrides)
    return ApprovedRefBundle(**base)


def candidate():
    selected = select_learning_candidates([usage_log()])
    assert len(selected) == 1
    return selected[0]


def gate_input(**kwargs):
    return build_learning_gate_input(candidate(), approved_bundle(), envelope(), **kwargs)


def test_select_learning_candidates_requires_digest_only_allow_real_record():
    logs = [
        usage_log(),
        usage_log(log_id="ulog-no-candidate", learning_candidate=False),
        usage_log(log_id="ulog-policy-deny", policy_decision="deny", integration_mode="contract_only", real_validation_done=False),
        usage_log(log_id="ulog-contract-only", integration_mode="contract_only", real_validation_done=False),
        usage_log(log_id="ulog-raw", raw_text_logged=True),
    ]

    selected = select_learning_candidates(logs)

    assert [item.source_usage_log_id for item in selected] == ["ulog-pr-e-001"]
    assert selected[0].label == {
        "intent_label": "memory_search",
        "target_box_id": "helper1",
        "quality": "good",
    }


def test_learning_allowed_false_drops_without_event():
    data = build_learning_gate_input(candidate(), approved_bundle(), envelope(learning_allowed=False))

    result = create_learning_event_result(data, now=NOW)

    assert result.event is None
    assert result.drop_reason == "LEARNING_NOT_ALLOWED"


def test_approved_text_ref_missing_drops_even_with_digest():
    data = build_learning_gate_input(candidate(), None, envelope())
    data["approved_text_digest"] = digest("digest alone is not enough")
    data["sanitized_summary_digest"] = digest("summary")
    data["dlp_result"] = {
        "passed": True,
        "pii_detected": False,
        "secret_detected": False,
        "policy_violation": False,
    }

    result = create_learning_event_result(data, now=NOW)

    assert result.event is None
    assert result.drop_reason == "APPROVED_TEXT_REF_MISSING"


def test_policy_non_allow_usage_log_is_not_candidate():
    denied = usage_log(policy_decision="deny", integration_mode="contract_only", real_validation_done=False)

    assert select_learning_candidates([denied]) == []


def test_dlp_failure_blocks_learning_event_creation():
    bundle = approved_bundle(runtime_text_for_dlp="담당자 이메일 owner@example.com")
    data = build_learning_gate_input(candidate(), bundle, envelope())

    result = create_learning_event_result(data, now=NOW)

    assert result.event is None
    assert result.drop_reason == "DLP_FAILED"


def test_learning_event_schema_self_validates_and_unknown_field_fails():
    result = create_learning_event_result(gate_input(), now=NOW)
    assert result.drop_reason is None
    event = result.event
    assert event is not None

    validate_learning_event(event)
    with pytest.raises(ValidationError):
        validate_learning_event({**event, "unexpected": True})


def test_verified_for_training_only_after_approved_policy_and_dlp_pass():
    event = create_learning_event_result(gate_input(), now=NOW).event
    assert event is not None
    assert event["status"] == "CANDIDATE"
    assert event["verified_for_training"] is False

    assert approve_learning_event(event, {"decision": "needs_review", "approver_role": "manager", "reason_code": "NOT_READY"}, now=NOW) is None
    approved = approve_learning_event(
        event,
        {"decision": "approved", "approver_role": "manager", "reason_code": "APPROVED_FOR_TRAINING"},
        now=NOW,
    )

    assert approved is not None
    assert approved["status"] == "APPROVED"
    assert approved["verified_for_training"] is True
    validate_learning_event(approved)


def test_mislabel_is_blocked_by_learning_event_schema():
    data = gate_input()
    data["label"] = {
        "intent_label": "accounting_classify",
        "target_box_id": "helper1",
        "quality": "good",
    }

    result = create_learning_event_result(data, now=NOW)

    assert result.event is None
    assert result.drop_reason == "SCHEMA_VALIDATION_FAILED"


def test_reject_transition_never_verifies_training():
    event = create_learning_event_result(gate_input(), now=NOW).event
    assert event is not None

    rejected = reject_learning_event(event)

    assert rejected["status"] == "REJECTED"
    assert rejected["verified_for_training"] is False
    validate_learning_event(rejected)


def test_usage_log_is_immutable_and_link_index_is_separate(tmp_path):
    source = usage_log()
    original = copy.deepcopy(source)
    selected = select_learning_candidates([source])[0]
    data = build_learning_gate_input(selected, approved_bundle(), envelope())
    event = create_learning_event_result(data, now=NOW).event
    assert event is not None

    store = LearningEventStore(tmp_path / "learning_events.jsonl")
    stored = store.append(event)

    assert source == original
    assert stored["source_usage_log_id"] == source["log_id"]
    assert store.linked_event_id(source["log_id"]) == stored["learning_event_id"]
    assert "learning_event_id" not in source
