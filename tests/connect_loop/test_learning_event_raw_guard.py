from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from butler_pc_core.connect_loop.dlp_guard import assert_no_raw_or_secret_material, scan_runtime_text
from butler_pc_core.connect_loop.learning_candidate_gate import (
    ApprovedRefBundle,
    build_learning_gate_input,
    create_learning_event_result,
    select_learning_candidates,
)

NOW = datetime(2026, 5, 31, tzinfo=timezone.utc)


def digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def usage_log(**overrides):
    base = {
        "log_id": "ulog-pr-e-raw-guard-001",
        "timestamp": "2026-05-31T00:00:00Z",
        "request_id": "req-pr-e-raw-guard-001",
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


def candidate():
    return select_learning_candidates([usage_log()])[0]


def test_dlp_guard_returns_booleans_only_without_matched_raw_text():
    owner_email = "owner" + "@" + "example.com"
    local_path = "/" + "Users/example/report.docx"
    raw = f"담당자 {owner_email} token=secret-value {local_path}"

    result = scan_runtime_text(raw)

    assert result == {
        "passed": False,
        "pii_detected": True,
        "secret_detected": True,
        "policy_violation": True,
    }
    assert raw not in str(result)
    assert owner_email not in str(result)
    assert "secret-value" not in str(result)
    assert local_path not in str(result)


def test_dlp_guard_catches_hyphenated_sk_project_tokens():
    secret_token = "sk-" + "proj-alpha-beta-1234567890"
    secret_text = f"local runtime secret {secret_token} should never pass"

    result = scan_runtime_text(secret_text)

    assert result["passed"] is False
    assert result["secret_detected"] is True
    assert "sk-proj-alpha" not in str(result)


def test_raw_guard_blocks_hyphenated_sk_project_tokens():
    secret_token = "sk-" + "proj-alpha-beta-1234567890"
    try:
        assert_no_raw_or_secret_material({"digest_only_note": secret_token})
    except ValueError as exc:
        assert str(exc) == "RAW_OR_SECRET_VALUE_FORBIDDEN"
    else:  # pragma: no cover
        raise AssertionError("hyphenated sk token was not blocked")


def test_raw_like_keys_are_blocked():
    try:
        assert_no_raw_or_secret_material({"raw_text": "not allowed"})
    except ValueError as exc:
        assert str(exc) == "RAW_OR_SECRET_FIELD_FORBIDDEN"
    else:  # pragma: no cover
        raise AssertionError("raw key was not blocked")


def test_local_path_like_approved_reference_is_blocked():
    local_ref = "file://" + "/" + "Users/kimsunghoon/Desktop/source.docx"
    bundle = ApprovedRefBundle(
        approved_text_ref=local_ref,
        approved_text_digest=digest("approved"),
        sanitized_summary_digest=digest("summary"),
        runtime_text_for_dlp="정제 텍스트",
    )
    data = build_learning_gate_input(candidate(), bundle, envelope())

    result = create_learning_event_result(data, now=NOW)

    assert result.event is None
    assert result.drop_reason == "APPROVED_TEXT_REF_FORBIDDEN"


def test_learning_gate_source_contains_no_training_or_model_artifact_code():
    paths = [
        Path("butler_pc_core/connect_loop/learning_candidate_gate.py"),
        Path("butler_pc_core/connect_loop/dlp_guard.py"),
        Path("butler_pc_core/connect_loop/learning_event_store.py"),
        Path("butler_pc_core/connect_loop/learning_event_schema.py"),
    ]
    forbidden = (
        "actual_" + "training",
        "Train" + "er(",
        "save_" + "pretrained",
        "adapter_" + "model",
        "gg" + "uf",
        "safe" + "tensors",
    )

    for path in paths:
        source = path.read_text(encoding="utf-8")
        for term in forbidden:
            assert term not in source
