"""maindev v1.2 이식 — usage_log request_id 상관/ digest-only 검증 (PR-B 미들웨어 소비)."""
from __future__ import annotations

import json

from butler_pc_core.sidecar.middleware.usage_accumulator import build_usage_log


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


def test_usage_log_keeps_request_id_and_digest_only():
    headers = _Headers({
        "x-request-id": "req-sidecar-e2e",
        "x-routing-confidence": "0.91",
        "x-learning-candidate": "0",
    })
    response_body = json.dumps({
        "integration_mode": "real",
        "real_validation_done": True,
        "results": [{"source_digest": "sha256:" + "0" * 64}],
        "external_send_zero": True,
        "raw_text_logged": False,
    }).encode("utf-8")
    record = build_usage_log(
        path="/v1/helpers/1/search",
        status_code=200,
        request_body=b'{"query":"runtime-only"}',
        response_body=response_body,
        headers=headers,
        latency_ms=12.34,
    )
    assert record["request_id"] == "req-sidecar-e2e"
    assert record["integration_mode"] == "real"
    # endpoint real_validation_done 은 응답값 기준(코덱스/계약 정합)
    assert record["real_validation_done"] is True
    assert record["external_send_zero"] is True
    assert record["raw_text_logged"] is False
    assert record["source_digests"] == ["sha256:" + "0" * 64]
    # 원문(runtime-only)이 digest-only 레코드에 절대 노출되지 않는다
    assert "runtime-only" not in json.dumps(record, ensure_ascii=False)


def test_usage_log_deny_decision_is_non_real():
    """policy_decision=deny 면 PR-B 통첨 불변식으로 contract_only/false (응답값 기준 정합)."""
    headers = _Headers({"x-request-id": "req-deny-1"})
    response_body = json.dumps({
        "integration_mode": "real",
        "real_validation_done": True,
        "external_send_zero": True,
        "raw_text_logged": False,
    }).encode("utf-8")
    record = build_usage_log(
        path="/v1/helpers/1/search",
        status_code=403,
        request_body=b"{}",
        response_body=response_body,
        headers=headers,
        latency_ms=5.0,
    )
    assert record["policy_decision"] == "deny"
    assert record["integration_mode"] == "contract_only"
    assert record["real_validation_done"] is False
