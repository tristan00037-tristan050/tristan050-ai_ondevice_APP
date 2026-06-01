"""PR-E v2.2 root-review matrix for the single persisted-safety guard."""
from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone

import pytest

from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text
from butler_pc_core.connect_loop.learning_candidate_gate import (
    ApprovedRefBundle,
    approve_learning_event,
    build_learning_gate_input,
    create_learning_event_result,
    expire_learning_event,
    reject_learning_event,
    select_learning_candidates,
)
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore
from butler_pc_core.connect_loop.persisted_safety import (
    PersistedSafetyViolation,
    _enforce_persisted_safety,
)

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _d(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _usage_log(**overrides):
    base = {
        "log_id": "ulog-v22-001",
        "timestamp": "2026-06-01T00:00:00Z",
        "request_id": "req-v22-001",
        "device_id_digest": _d("device"),
        "tenant_id_digest": _d("tenant"),
        "department_id_digest": _d("department"),
        "request_digest": _d("request"),
        "intent_label": "memory_search",
        "box_id": "helper1",
        "endpoint": "POST /v1/helpers/1/search",
        "routing_confidence": 0.93,
        "integration_mode": "real",
        "real_validation_done": True,
        "result_digest": _d("result"),
        "source_digests": [_d("source")],
        "policy_decision": "allow",
        "policy_reason_code": "OK",
        "latency_ms": 12.5,
        "external_send_zero": True,
        "raw_text_logged": False,
        "learning_candidate": True,
        "learning_event_created": False,
        "retention_class": "audit_digest_only",
        "created_by_component": "connect_loop.usage_accumulator",
        "schema_hash": _d("usage_log_schema"),
        "schema_version": "usage_log.v1.1",
    }
    base.update(overrides)
    return base


def _envelope(**overrides):
    base = {
        "learning_allowed": True,
        "tenant_scope": "device",
        "retention_days": 30,
        "expires_at": "2026-12-31T00:00:00Z",
        "reason_code": "LEARNING_ALLOWED_SANITIZED",
    }
    base.update(overrides)
    return base


def _bundle(**overrides):
    base = {
        "approved_text_ref": "vault://learning-events/v22-001",
        "approved_text_digest": _d("approved"),
        "sanitized_summary_digest": _d("summary"),
        "runtime_text_for_dlp": "정제된 digest-only 요약",
    }
    base.update(overrides)
    return ApprovedRefBundle(**base)


def _candidate():
    selected = select_learning_candidates([_usage_log()])
    assert len(selected) == 1
    return selected[0]


def _gate_input(**bundle_overrides):
    return build_learning_gate_input(_candidate(), _bundle(**bundle_overrides), _envelope())


def _event():
    result = create_learning_event_result(_gate_input(), now=NOW)
    assert result.drop_reason is None
    assert result.event is not None
    return result.event


def _email_ref() -> str:
    return "vault://learning/" + "alice" + "@" + "example.com"


def _linux_home_path() -> str:
    return "/" + "home/alice/customer_notes.txt"


def _linux_tmp_path() -> str:
    return "/" + "tmp/export"


def _private_tmp_path() -> str:
    return "/" + "private/tmp/export"


def _mac_users_path() -> str:
    return "/" + "Users/alice/customer_notes.txt"


def _volume_path() -> str:
    return "/" + "Volumes/Drive/customer_notes.txt"


def _windows_path() -> str:
    return "C:" + "\\Users\\alice\\customer_notes.txt"


def _windows_slash_path() -> str:
    return "C:" + "/Projects/customer_notes.txt"


def _unc_path() -> str:
    return "\\\\" + "server\\share\\customer_notes.txt"


def _file_url() -> str:
    return "file://" + _linux_home_path()


@pytest.mark.parametrize(
    "path_factory",
    [
        _mac_users_path,
        _linux_home_path,
        _linux_tmp_path,
        _private_tmp_path,
        _volume_path,
        _windows_path,
        _windows_slash_path,
        _unc_path,
        _file_url,
    ],
    ids=[
        "mac_users",
        "linux_home",
        "linux_tmp",
        "private_tmp",
        "volume",
        "windows",
        "windows_slash",
        "unc",
        "file_url",
    ],
)
def test_scan_runtime_text_blocks_os_agnostic_paths(path_factory):
    result = scan_runtime_text("정제 후보 " + path_factory())

    assert result["passed"] is False
    assert result["policy_violation"] is True


@pytest.mark.parametrize(
    "value_factory",
    [
        _email_ref,
        _linux_home_path,
        lambda: "Bearer " + "abc1234567890",
        lambda: "AKIA" + "IOSFODNN7EXAMPLE",
        lambda: "token" + "=abc1234567890",
        lambda: "password" + "=abc1234567890",
        lambda: "api_key" + "=abc1234567890",
        lambda: "sk-" + "proj-AbC123def456GhI_789-jkl",
    ],
    ids=["email_pii", "linux_path", "bearer", "akia", "token", "password", "api_key", "sk_project"],
)
def test_enforce_persisted_safety_blocks_secret_path_pii_scalars(value_factory):
    with pytest.raises(PersistedSafetyViolation, match="PERSISTED_SCALAR_DLP_BLOCK"):
        _enforce_persisted_safety({"approved_text_ref": value_factory()})


@pytest.mark.parametrize(
    "phone_text",
    [
        "+1 415-555-1212",
        "(415) 555-1212",
        "+82 10-1234-5678",
        "+8210-1234-5678",
        "010-1234-5678",
    ],
    ids=[
        "intl_plus_one",
        "us_parenthesized",
        "korean_canonical_plus82",
        "korean_compact_plus82",
        "korean_mobile",
    ],
)
def test_scan_runtime_text_blocks_international_phone_pii(phone_text):
    result = scan_runtime_text("정제 후보 연락처 " + phone_text)

    assert result["passed"] is False
    assert result["pii_detected"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"raw_text": "blocked"},
        {"safe_raw": "blocked"},
        {"raw_input_saved": True},
        {"raw_output_saved": True},
        {"sanitized_summary_saved": True},
    ],
    ids=["raw_text", "suffix_raw", "raw_input_saved_true", "raw_output_saved_true", "summary_saved_true"],
)
def test_enforce_persisted_safety_blocks_raw_fields_and_saved_true(payload):
    with pytest.raises(PersistedSafetyViolation, match="RAW_FIELD_OR_SAVED_TRUE"):
        _enforce_persisted_safety(payload)


def test_create_path_blocks_pii_reference_before_event_return():
    result = create_learning_event_result(_gate_input(approved_text_ref=_email_ref()), now=NOW)

    assert result.event is None
    assert result.drop_reason == "RAW_OR_SECRET_MATERIAL_FORBIDDEN"


def test_approve_path_blocks_mutated_candidate_before_return():
    event = _event()
    event["approved_text_ref"] = _email_ref()

    approved = approve_learning_event(
        event,
        {"decision": "approved", "approver_role": "manager", "reason_code": "APPROVED_FOR_TRAINING"},
        now=NOW,
    )

    assert approved is None


def test_reject_path_blocks_mutated_candidate_before_return():
    event = _event()
    event["approved_text_ref"] = _email_ref()

    with pytest.raises(PersistedSafetyViolation, match="PERSISTED_SCALAR_DLP_BLOCK"):
        reject_learning_event(event)


def test_expire_path_blocks_mutated_candidate_before_return():
    event = _event()
    event["approved_text_ref"] = _email_ref()

    with pytest.raises(PersistedSafetyViolation, match="PERSISTED_SCALAR_DLP_BLOCK"):
        expire_learning_event(event, now=NOW)


def test_expired_approval_path_cannot_bypass_expire_guard():
    event = _event()
    event["expires_at"] = "2026-05-01T00:00:00Z"
    event["approved_text_ref"] = _email_ref()

    with pytest.raises(PersistedSafetyViolation, match="PERSISTED_SCALAR_DLP_BLOCK"):
        approve_learning_event(
            event,
            {"decision": "approved", "approver_role": "manager", "reason_code": "APPROVED_FOR_TRAINING"},
            now=NOW,
        )


def test_store_append_path_blocks_mutated_candidate_before_jsonl_write(tmp_path):
    event = _event()
    event["approved_text_ref"] = _email_ref()
    jsonl_path = tmp_path / "learning_events.jsonl"
    store = LearningEventStore(jsonl_path)

    with pytest.raises(PersistedSafetyViolation, match="PERSISTED_SCALAR_DLP_BLOCK"):
        store.append(event)

    assert not jsonl_path.exists()


def test_safe_lifecycle_paths_still_return_copies_and_pass_store(tmp_path):
    event = _event()
    approved = approve_learning_event(
        event,
        {"decision": "approved", "approver_role": "manager", "reason_code": "APPROVED_FOR_TRAINING"},
        now=NOW,
    )
    rejected = reject_learning_event(event)
    expired_source = copy.deepcopy(event)
    expired_source["expires_at"] = "2026-05-01T00:00:00Z"
    expired = expire_learning_event(expired_source, now=NOW)

    assert approved is not None
    assert approved["status"] == "APPROVED"
    assert rejected["status"] == "REJECTED"
    assert expired["status"] == "EXPIRED"

    stored = LearningEventStore(tmp_path / "learning_events.jsonl").append(event)
    assert stored == event
    assert stored is not event
