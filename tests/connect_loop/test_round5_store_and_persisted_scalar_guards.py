"""Codex round-5 회귀 방지 (2026-06-01, PR #769).

[P2-1] LearningEventStore는 source_usage_log_id 당 learning_event 1개만 허용한다.
상위 usage_log.learning_event_created 플래그 갱신이 늦거나 retry/backfill이 재실행되어도
learning_event_link_index를 덮어쓰거나 JSONL에 두 번째 row를 남기면 안 된다.

[P2-2] persisted scalar guard는 secret/local path뿐 아니라 PII도 차단한다.
runtime_text_for_dlp가 깨끗하더라도 approved_text_ref 같은 저장 필드에
email PII가 들어가면 fail-closed 되어야 한다.
"""
from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone

import pytest

from butler_pc_core.connect_loop.dlp_guard import assert_no_raw_or_secret_material
from butler_pc_core.connect_loop.learning_candidate_gate import (
    ApprovedRefBundle,
    approve_learning_event,
    build_learning_gate_input,
    create_learning_event_result,
    select_learning_candidates,
)
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _d(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _usage_log(**overrides):
    base = {
        "log_id": "ulog-r5-001",
        "timestamp": "2026-06-01T00:00:00Z",
        "request_id": "req-r5-001",
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
        "approved_text_ref": "vault://learning-events/r5-001",
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


def _pii_ref() -> str:
    return "vault://learning/" + "alice" + "@" + "example.com"


def _event():
    data = build_learning_gate_input(
        _candidate(),
        _bundle(),
        _envelope(),
    )
    result = create_learning_event_result(data, now=NOW)
    assert result.drop_reason is None
    assert result.event is not None
    return result.event


def test_learning_event_store_rejects_duplicate_source_usage_log_without_overwrite(tmp_path):
    """같은 source_usage_log_id의 두 번째 event는 index overwrite/JSONL append 없이 차단된다."""
    path = tmp_path / "learning_events.jsonl"
    first = _event()
    second = copy.deepcopy(first)
    second["learning_event_id"] = "lev-r5-second-event"

    store = LearningEventStore(path)
    stored = store.append(first)

    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_USAGE_LOG"):
        store.append(second)

    assert store.linked_event_id(first["source_usage_log_id"]) == stored["learning_event_id"]
    assert store.get(stored["learning_event_id"]) == stored
    assert store.get(second["learning_event_id"]) is None
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert stored["learning_event_id"] in lines[0]
    assert second["learning_event_id"] not in lines[0]


def test_learning_event_store_hydrates_source_index_from_jsonl_before_retry(tmp_path):
    """프로세스 재시작 후 jsonl_path에서 index를 복원해 retry 중복 append를 차단한다."""
    path = tmp_path / "learning_events.jsonl"
    first = _event()
    second = copy.deepcopy(first)
    second["learning_event_id"] = "lev-r5-after-restart"

    LearningEventStore(path).append(first)
    reopened = LearningEventStore(path)

    assert reopened.linked_event_id(first["source_usage_log_id"]) == first["learning_event_id"]
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_USAGE_LOG"):
        reopened.append(second)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_persisted_scalar_guard_blocks_email_inside_reference_value():
    """secret/local path가 아니어도 persisted scalar 안의 email PII는 저장 금지."""
    with pytest.raises(ValueError, match="RAW_OR_SECRET_VALUE_FORBIDDEN"):
        assert_no_raw_or_secret_material({"approved_text_ref": _pii_ref()})


def test_learning_gate_blocks_pii_inside_approved_text_ref_even_when_runtime_dlp_is_clean():
    """runtime_text_for_dlp가 clean이어도 저장 필드의 PII ref는 event 생성 전 차단된다."""
    data = build_learning_gate_input(
        _candidate(),
        _bundle(approved_text_ref=_pii_ref()),
        _envelope(),
    )

    result = create_learning_event_result(data, now=NOW)

    assert result.event is None
    assert result.drop_reason == "RAW_OR_SECRET_MATERIAL_FORBIDDEN"


def test_approve_learning_event_rejects_candidate_with_pii_reference_value():
    """외부에서 변형된 candidate event도 approval 단계에서 PII scalar를 통과시키지 않는다."""
    event = _event()
    event["approved_text_ref"] = _pii_ref()

    approved = approve_learning_event(
        event,
        {"decision": "approved", "approver_role": "manager", "reason_code": "APPROVED_FOR_TRAINING"},
        now=NOW,
    )

    assert approved is None
