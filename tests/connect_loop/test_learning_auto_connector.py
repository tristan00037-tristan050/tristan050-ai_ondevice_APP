"""수정2 검증 — learning_auto_connector (게이트 우회 0·위조 0).

필수 테스트:
  · invalid/비후보 usage_log → connector 가 게이트 event 를 만들지 않는다(미호출 동등).
  · 후보지만 approved_ref/policy envelope 없음 → 위조 없이 안전 drop.
  · 후보 + approved_ref + envelope → 게이트 통과 시 learning_event 생성·영속.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from butler_pc_core.connect_loop.learning_auto_connector import (
    DROP_APPROVED_REF_OR_ENVELOPE_MISSING,
    DROP_NOT_ELIGIBLE,
    run_learning_auto_connection,
)
from butler_pc_core.connect_loop.learning_candidate_gate import ApprovedRefBundle
from butler_pc_core.connect_loop.learning_event_schema import validate_learning_event
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore

NOW = datetime(2026, 5, 31, tzinfo=timezone.utc)


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def usage_log(**overrides):
    base = {
        "log_id": "ulog-conn-001",
        "timestamp": "2026-05-31T00:00:00Z",
        "request_id": "req-conn-001",
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


def approved_bundle():
    return ApprovedRefBundle(
        approved_text_ref="vault://learning-events/conn-001",
        approved_text_digest=digest("approved sanitized text"),
        sanitized_summary_digest=digest("summary"),
        runtime_text_for_dlp="정제된 업무 지식 요약",
    )


# ── 테스트5: invalid/비후보는 connector 가 event 를 만들지 않는다 ──────────────
def test_invalid_usage_log_not_connected():
    """비후보(learning_candidate=False) → 게이트 미호출 동등, event 0."""
    result = run_learning_auto_connection(
        usage_log(learning_candidate=False),
        approved_ref_bundle=approved_bundle(),
        policy_task_envelope=envelope(),
        now=NOW,
    )
    assert result.event is None
    assert result.learning_event_created is False
    assert result.drop_reason == DROP_NOT_ELIGIBLE


def test_schema_invalid_usage_log_not_connected():
    """스키마 위반(retention_class 변조) → NOT_ELIGIBLE, event 0."""
    bad = usage_log()
    bad["retention_class"] = "keep_forever"  # const 위반
    result = run_learning_auto_connection(
        bad,
        approved_ref_bundle=approved_bundle(),
        policy_task_envelope=envelope(),
        now=NOW,
    )
    assert result.event is None
    assert result.drop_reason == DROP_NOT_ELIGIBLE


# ── 테스트6: approved_ref/envelope 없으면 위조 없이 안전 drop ──────────────────
def test_candidate_without_approved_ref_safe_drop():
    result = run_learning_auto_connection(usage_log(), now=NOW)
    assert result.event is None
    assert result.learning_event_created is False
    assert result.drop_reason == DROP_APPROVED_REF_OR_ENVELOPE_MISSING


def test_candidate_with_ref_but_no_envelope_safe_drop():
    result = run_learning_auto_connection(
        usage_log(), approved_ref_bundle=approved_bundle(), now=NOW
    )
    assert result.event is None
    assert result.drop_reason == DROP_APPROVED_REF_OR_ENVELOPE_MISSING


# ── 테스트7: approved_ref + envelope 있으면 게이트 통해 event 생성 ─────────────
def test_candidate_with_approved_ref_creates_event():
    store = LearningEventStore()
    result = run_learning_auto_connection(
        usage_log(),
        approved_ref_bundle=approved_bundle(),
        policy_task_envelope=envelope(),
        event_store=store,
        now=NOW,
    )
    assert result.drop_reason is None
    assert result.learning_event_created is True
    assert result.event is not None
    # 게이트가 만든 event 는 스키마 유효 + source 연결이 정확해야 한다.
    validate_learning_event(result.event)
    assert result.event["source_usage_log_id"] == "ulog-conn-001"
    assert result.event["status"] == "CANDIDATE"
    assert result.event["raw_input_saved"] is False
    assert result.event["raw_output_saved"] is False
    # event_store 에 1건 영속.
    assert len(store.events) == 1


def test_gate_bypass_is_impossible_expired_envelope_drops():
    """게이트 우회 0: envelope 만료면 approved_ref 가 있어도 event 0."""
    result = run_learning_auto_connection(
        usage_log(),
        approved_ref_bundle=approved_bundle(),
        policy_task_envelope=envelope(expires_at="2020-01-01T00:00:00Z"),
        now=NOW,
    )
    assert result.event is None
    assert result.learning_event_created is False
    assert result.drop_reason == "RETENTION_EXPIRED"
