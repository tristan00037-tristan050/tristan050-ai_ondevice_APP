"""Codex P1 정정 회귀 방지 (2026-05-31, PR #769).

게이트는 `gate_input["label"]`이 schema-consistent하더라도 source usage_log의
intent_label/box_id와 다르면 LABEL_SOURCE_DRIFT로 드롭해야 한다. 그렇지 않으면
caller가 라벨을 다른 schema-consistent 값으로 주입/변형(예: memory_search 출처
로그 + form_convert 라벨)했을 때, learning_event 스키마는 라벨 내부 일관성만
보므로 통과하고, source_usage_log_id가 가리키는 감사 로그와 학습된 task가
어긋나 wrong task로 학습된다.
"""
from __future__ import annotations

import hashlib

import pytest

from butler_pc_core.connect_loop.learning_candidate_gate import (
    ApprovedRefBundle,
    build_learning_gate_input,
    create_learning_event_result,
    select_learning_candidates,
)


def _d(v: str) -> str:
    return "sha256:" + hashlib.sha256(v.encode("utf-8")).hexdigest()


def _usage_log(intent: str = "memory_search", box: str = "helper1", endpoint: str = "POST /v1/helpers/1/search"):
    return {
        "log_id": "ulog-drift-001",
        "timestamp": "2026-05-31T00:00:00Z",
        "request_id": "req-drift-001",
        "device_id_digest": _d("dev"),
        "tenant_id_digest": _d("tenant"),
        "department_id_digest": _d("dept"),
        "request_digest": _d("req"),
        "intent_label": intent,
        "box_id": box,
        "endpoint": endpoint,
        "routing_confidence": 0.92,
        "integration_mode": "real",
        "real_validation_done": True,
        "result_digest": _d("res"),
        "source_digests": [_d("s")],
        "policy_decision": "allow",
        "policy_reason_code": "OK",
        "latency_ms": 10.0,
        "external_send_zero": True,
        "raw_text_logged": False,
        "learning_candidate": True,
        "learning_event_created": False,
        "retention_class": "audit_digest_only",
        "created_by_component": "connect_loop.usage_accumulator",
        "schema_hash": _d("schema"),
        "schema_version": "usage_log.v1.1",
    }


def _envelope():
    return {
        "learning_allowed": True,
        "tenant_scope": "device",
        "retention_days": 30,
        "expires_at": "2026-12-31T00:00:00Z",
        "reason_code": "LEARNING_ALLOWED_SANITIZED",
    }


def _bundle():
    return ApprovedRefBundle(
        approved_text_ref="vault://learning-events/drift-001",
        approved_text_digest=_d("approved"),
        sanitized_summary_digest=_d("summary"),
        runtime_text_for_dlp="정제된 요약",
    )


def _gate_input_from(usage_log: dict) -> dict:
    candidates = select_learning_candidates([usage_log])
    assert len(candidates) == 1
    return build_learning_gate_input(candidates[0], _bundle(), _envelope())


def test_happy_path_label_matches_source_passes():
    """label이 source usage_log와 일치하면 통과 (회귀 방지)."""
    gi = _gate_input_from(_usage_log())
    result = create_learning_event_result(gi)
    assert result.drop_reason is None, result.drop_reason
    assert result.event is not None
    assert result.event["label"]["intent_label"] == "memory_search"
    assert result.event["label"]["target_box_id"] == "helper1"


def test_label_intent_drift_drops_with_label_source_drift():
    """결함 #1 핵심: caller가 label.intent_label을 source와 다르게 주입하면 드롭."""
    gi = _gate_input_from(_usage_log(intent="memory_search", box="helper1"))
    # caller가 schema-consistent하게 form_convert/box=2로 변형
    gi["label"]["intent_label"] = "form_convert"
    gi["label"]["target_box_id"] = "2"
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "LABEL_SOURCE_DRIFT"


def test_label_target_box_drift_drops_with_label_source_drift():
    """label.target_box_id만 source와 달라도 드롭 (intent_label 일치해도)."""
    gi = _gate_input_from(_usage_log(intent="memory_search", box="helper1"))
    gi["label"]["target_box_id"] = "5"  # intent는 memory_search인데 box는 5(accounting)
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "LABEL_SOURCE_DRIFT"


def test_label_intent_drift_only_drops_with_label_source_drift():
    """intent_label만 source와 달라도 드롭 (target_box_id 일치해도)."""
    gi = _gate_input_from(_usage_log(intent="accounting_classify", box="5", endpoint="POST /accounting/classify"))
    gi["label"]["intent_label"] = "draft_write"  # source는 accounting인데 라벨은 draft_write
    # target_box_id=5는 source와 같음
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "LABEL_SOURCE_DRIFT"


def test_missing_label_drops_with_label_missing():
    """label 자체가 누락되면 LABEL_MISSING으로 드롭."""
    gi = _gate_input_from(_usage_log())
    gi["label"] = None
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "LABEL_MISSING"
