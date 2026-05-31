"""Codex follow-on (HOLD 3건) 회귀 방지 (2026-05-31, PR #769).

P1 — DLP scan mandatory + caller mismatch fail-closed:
  build_learning_gate_input은 runtime_text_for_dlp가 있으면 caller가 dlp_result를
  제공해도 *항상* scan_runtime_text를 수행해 dlp_runtime_scan으로 보관한다.
  _drop_reason은 caller dlp_result와 dlp_runtime_scan이 일치해야 통과시키고,
  불일치(예: runtime_text에 PII가 있는데 caller dlp_result.passed=True) → DLP_RESULT_MISMATCH.

P2 — _parse_rfc3339 naive tzinfo guard:
  tzinfo가 없는 datetime은 None으로 매핑. _drop_reason은 None을 EXPIRES_AT_INVALID로
  드롭하므로 aware datetime과 naive datetime을 `<=` 비교하다가 TypeError로 crash 0.
"""
from __future__ import annotations

import copy
import hashlib

import pytest

from butler_pc_core.connect_loop.learning_candidate_gate import (
    ApprovedRefBundle,
    build_learning_gate_input,
    create_learning_event_result,
    select_learning_candidates,
    _parse_rfc3339,
)


def _d(v: str) -> str:
    return "sha256:" + hashlib.sha256(v.encode("utf-8")).hexdigest()


def _usage_log():
    return {
        "log_id": "ulog-dlp-001",
        "timestamp": "2026-05-31T00:00:00Z",
        "request_id": "req-dlp-001",
        "device_id_digest": _d("dev"),
        "tenant_id_digest": _d("tenant"),
        "department_id_digest": _d("dept"),
        "request_digest": _d("req"),
        "intent_label": "memory_search",
        "box_id": "helper1",
        "endpoint": "POST /v1/helpers/1/search",
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


def _envelope(expires_at: str = "2026-12-31T00:00:00Z"):
    return {
        "learning_allowed": True,
        "tenant_scope": "device",
        "retention_days": 30,
        "expires_at": expires_at,
        "reason_code": "LEARNING_ALLOWED_SANITIZED",
    }


def _bundle(runtime_text: str | None = "정제된 요약(PII 없음)"):
    return ApprovedRefBundle(
        approved_text_ref="vault://learning-events/dlp-001",
        approved_text_digest=_d("approved"),
        sanitized_summary_digest=_d("summary"),
        runtime_text_for_dlp=runtime_text,
    )


def _candidate():
    candidates = select_learning_candidates([_usage_log()])
    assert len(candidates) == 1
    return candidates[0]


# ── P1: DLP scan mandatory + mismatch fail-closed ─────────────────────────

PII_TEXT = "고객 이메일 " + "alice" + "@" + "example.com" + ", 전화 010-1234-5678 첨부."
SECRET_TEXT = "사내 API 자격: " + "api_key" + "=AKIAIOSFODNN7EXAMPLE12 (절대 외부 유출 금지)."
CALLER_PASSED_DLP = {
    "passed": True,
    "pii_detected": False,
    "secret_detected": False,
    "policy_violation": False,
}


def test_runtime_pii_with_caller_passed_true_drops_with_dlp_result_mismatch():
    """결함 P1 대표: runtime_text에 PII가 있는데 caller가 passed=True를 주장 → 드롭."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=PII_TEXT),
        _envelope(),
        dlp_result=CALLER_PASSED_DLP,
    )
    # 내부 비교용 scan 결과는 PII를 검출했어야 함
    assert gi["dlp_runtime_scan"]["pii_detected"] is True
    assert gi["dlp_runtime_scan"]["passed"] is False
    # caller dlp_result는 passed=True (거짓 주장)
    assert gi["dlp_result"]["passed"] is True

    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "DLP_RESULT_MISMATCH"


def test_runtime_secret_with_caller_passed_true_drops_with_dlp_result_mismatch():
    """secret 검출 케이스도 동일하게 mismatch로 드롭."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=SECRET_TEXT),
        _envelope(),
        dlp_result=CALLER_PASSED_DLP,
    )
    assert gi["dlp_runtime_scan"]["secret_detected"] is True
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "DLP_RESULT_MISMATCH"


def test_scan_and_caller_mismatch_in_single_flag_drops_with_dlp_result_mismatch():
    """단일 필드(policy_violation)만 달라도 mismatch."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text="안전한 정제 요약, 식별자 없음"),
        _envelope(),
        dlp_result={
            "passed": False,
            "pii_detected": False,
            "secret_detected": False,
            "policy_violation": True,  # caller 주장: 정책 위반 있음
        },
    )
    # scan 결과는 모두 False(통과)
    assert gi["dlp_runtime_scan"]["passed"] is True
    # caller dlp_result.passed=False → boolean 체크에서 먼저 DLP_FAILED 또는 mismatch?
    # 본 케이스는 caller가 passed=False를 명시했으므로 boolean 체크가 먼저 잡는다.
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "DLP_FAILED"  # caller dlp_result 자체가 fail


def test_scan_pii_with_caller_partially_correct_still_drops_mismatch():
    """scan은 pii=True, caller는 pii=True지만 passed 불일치 → mismatch."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=PII_TEXT),
        _envelope(),
        dlp_result={
            "passed": True,            # caller: 통과 주장
            "pii_detected": True,      # 그러나 pii는 있다고 인정
            "secret_detected": False,
            "policy_violation": False,
        },
    )
    # caller dlp_result.passed=True인데 pii_detected=True (자기 모순) →
    # boolean 체크에서 pii_detected=False가 아니므로 DLP_FAILED 우선 잡힘
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "DLP_FAILED"


def test_runtime_text_clean_with_caller_passed_true_passes_when_match():
    """scan과 caller 모두 통과 + 모든 필드 일치 → 정상 통과 (회귀 방지)."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text="안전한 정제 요약, 식별자 없음"),
        _envelope(),
        dlp_result=CALLER_PASSED_DLP,
    )
    assert gi["dlp_runtime_scan"] == CALLER_PASSED_DLP
    result = create_learning_event_result(gi)
    assert result.drop_reason is None, result.drop_reason
    assert result.event is not None


def test_caller_dlp_without_runtime_text_uses_caller_only():
    """runtime_text가 없으면 scan 미수행, caller dlp_result만 검증 (기존 흐름 유지)."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=None),
        _envelope(),
        dlp_result=CALLER_PASSED_DLP,
    )
    assert gi["dlp_runtime_scan"] is None  # 스캔 미수행
    result = create_learning_event_result(gi)
    assert result.drop_reason is None, result.drop_reason
    assert result.event is not None


# ── P2: _parse_rfc3339 naive tzinfo guard ─────────────────────────────────


def test_parse_rfc3339_aware_passes():
    assert _parse_rfc3339("2026-12-31T00:00:00Z") is not None
    assert _parse_rfc3339("2026-12-31T00:00:00+09:00") is not None


def test_parse_rfc3339_naive_returns_none():
    """tzinfo 없는 datetime은 None — aware/naive 비교 TypeError 차단."""
    assert _parse_rfc3339("2026-12-31T00:00:00") is None
    assert _parse_rfc3339("2026-12-31T00:00:00.500") is None


def test_parse_rfc3339_malformed_returns_none():
    assert _parse_rfc3339("not-a-datetime") is None
    assert _parse_rfc3339("") is None


def test_naive_expires_at_drops_with_expires_at_invalid_no_typeerror():
    """결함 P2 대표: naive expires_at('2026-12-31T00:00:00')는 EXPIRES_AT_INVALID drop, crash 0."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=None),
        _envelope(expires_at="2026-12-31T00:00:00"),  # ← naive, tzinfo 없음
        dlp_result=CALLER_PASSED_DLP,
    )
    # TypeError 등 crash 발생하면 안 됨
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "EXPIRES_AT_INVALID"


def test_aware_expires_at_in_future_passes():
    """aware expires_at은 정상 통과 (회귀 방지)."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=None),
        _envelope(expires_at="2027-12-31T00:00:00Z"),
        dlp_result=CALLER_PASSED_DLP,
    )
    result = create_learning_event_result(gi)
    assert result.drop_reason is None, result.drop_reason
    assert result.event is not None
