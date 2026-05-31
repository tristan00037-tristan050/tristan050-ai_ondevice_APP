"""Codex round-4 회귀 방지 (2026-05-31, PR #769).

[P1] DLP regex가 `sk-proj-…`처럼 영문·숫자·하이픈·언더스코어가 섞인 장문 token도
    탐지하는지 잠근다(`_SECRET_RE` 회귀 보호). runtime_text_for_dlp에 그 패턴이
    포함되면 scan은 secret_detected=True를 산출하며, caller dlp_result에 따라
    DLP_FAILED 또는 DLP_RESULT_MISMATCH로 드롭된다.

[P2-1] _is_candidate_usage_log()는 `learning_event_created=True` 인 usage_log를
    후보에서 제외해야 한다(이미 학습 이벤트가 만들어진 로그를 다시 후보로 보지 않음,
    멱등성).

[P2-2] policy_task_envelope.tenant_scope 가 누락되거나 enum 외 값이면 event 빌드
    전 단계에서 TENANT_SCOPE_INVALID 로 드롭된다(`envelope["tenant_scope"]`
    KeyError 0).
"""
from __future__ import annotations

import hashlib

import pytest

from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text
from butler_pc_core.connect_loop.learning_candidate_gate import (
    ApprovedRefBundle,
    build_learning_gate_input,
    create_learning_event_result,
    select_learning_candidates,
)


def _d(v: str) -> str:
    return "sha256:" + hashlib.sha256(v.encode("utf-8")).hexdigest()


def _usage_log(**overrides):
    base = {
        "log_id": "ulog-r4-001",
        "timestamp": "2026-05-31T00:00:00Z",
        "request_id": "req-r4-001",
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


def _bundle(runtime_text: str | None = "안전한 정제 요약"):
    return ApprovedRefBundle(
        approved_text_ref="vault://learning-events/r4-001",
        approved_text_digest=_d("approved"),
        sanitized_summary_digest=_d("summary"),
        runtime_text_for_dlp=runtime_text,
    )


def _candidate():
    candidates = select_learning_candidates([_usage_log()])
    assert len(candidates) == 1
    return candidates[0]


# ── [P1] DLP regex: sk-proj-… 류 secret 탐지 회귀 잠금 ─────────────────

# 영문·숫자·하이픈·언더스코어 혼합 장문 token (실제 openai sk-proj-… 형식 모사)
SK_PROJ_TOKEN = "sk-proj-AbC123def456GhI_789-jkl"


@pytest.mark.parametrize("text", [
    f"OPENAI_API_KEY={SK_PROJ_TOKEN}",
    f"config: openai_token = {SK_PROJ_TOKEN}; restart",
    SK_PROJ_TOKEN,
])
def test_dlp_scan_detects_sk_proj_token(text):
    """[P1] sk-proj-… 류 token이 secret으로 탐지된다."""
    result = scan_runtime_text(text)
    assert result["secret_detected"] is True
    assert result["passed"] is False


def test_dlp_failed_drops_when_runtime_has_sk_proj_token_and_caller_omitted():
    """[P1] caller dlp_result 미명시 + runtime에 sk-proj- token → DLP_FAILED."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=f"key={SK_PROJ_TOKEN}"),
        _envelope(),
        dlp_result=None,  # caller 미명시 → scan 결과를 resolved_dlp로 채택
    )
    assert gi["dlp_result"]["secret_detected"] is True
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "DLP_FAILED"


def test_dlp_result_mismatch_drops_when_caller_claims_passed_for_sk_proj_token():
    """[P1] runtime에 sk-proj- token 있는데 caller passed=True 주장 → DLP_RESULT_MISMATCH."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=f"export OPENAI_KEY={SK_PROJ_TOKEN}"),
        _envelope(),
        dlp_result={
            "passed": True,
            "pii_detected": False,
            "secret_detected": False,  # caller 거짓 주장
            "policy_violation": False,
        },
    )
    assert gi["dlp_runtime_scan"]["secret_detected"] is True
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason in {"DLP_RESULT_MISMATCH", "DLP_FAILED"}
    # 본 케이스는 caller가 boolean을 모두 passed로 줬으므로 mismatch가 우선 작동
    assert result.drop_reason == "DLP_RESULT_MISMATCH"


# ── [P2-1] learning_event_created=True 인 usage_log는 후보 제외 ────────

def test_learning_event_created_true_excluded_from_candidates():
    """이미 학습 이벤트가 생성된 usage_log는 select가 반환 [] (멱등성)."""
    already = _usage_log(log_id="ulog-already", learning_event_created=True)
    assert select_learning_candidates([already]) == []


def test_mix_of_created_and_not_created_returns_only_not_created():
    """learning_event_created=True 1건 + =False 1건 → False 1건만 후보."""
    eligible = _usage_log(log_id="ulog-eligible", learning_event_created=False)
    already = _usage_log(log_id="ulog-already", learning_event_created=True)
    out = select_learning_candidates([eligible, already])
    assert [c.source_usage_log_id for c in out] == ["ulog-eligible"]


# ── [P2-2] tenant_scope 누락/invalid → TENANT_SCOPE_INVALID, KeyError 0 ─

def test_envelope_missing_tenant_scope_drops_without_keyerror():
    """[P2-2] envelope에서 tenant_scope 키 자체 누락 → TENANT_SCOPE_INVALID, crash 0."""
    env = _envelope()
    env.pop("tenant_scope")
    gi = build_learning_gate_input(_candidate(), _bundle(runtime_text=None), env)
    # crash 발생하면 안 됨 — KeyError 등 unhandled exception 0
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "TENANT_SCOPE_INVALID"


@pytest.mark.parametrize("bad", ["", "galaxy", None, 0, "DEVICE", "Team"])
def test_envelope_invalid_tenant_scope_drops_with_tenant_scope_invalid(bad):
    """[P2-2] enum {device,team,org} 외 값 → TENANT_SCOPE_INVALID."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=None),
        _envelope(tenant_scope=bad),
    )
    result = create_learning_event_result(gi)
    assert result.event is None
    assert result.drop_reason == "TENANT_SCOPE_INVALID"


@pytest.mark.parametrize("good", ["device", "team", "org"])
def test_envelope_valid_tenant_scope_passes(good):
    """회귀 0: enum 정합 값은 정상 통과."""
    gi = build_learning_gate_input(
        _candidate(),
        _bundle(runtime_text=None),
        _envelope(tenant_scope=good),
        dlp_result={
            "passed": True,
            "pii_detected": False,
            "secret_detected": False,
            "policy_violation": False,
        },
    )
    result = create_learning_event_result(gi)
    assert result.drop_reason is None, result.drop_reason
    assert result.event is not None
    assert result.event["tenant_scope"] == good
