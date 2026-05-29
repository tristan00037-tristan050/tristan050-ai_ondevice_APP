"""Connect Loop 계약 검증 테스트 (PR-A).

범위: 4종 JSON Schema 계약만 검증한다. 라우터/미들웨어/UI 구현은 후속 PR.

검증 항목:
  1) 4개 스키마가 draft-07 meta-schema에 대해 self-validate 통과
  2) 유효 샘플 4건이 각 스키마에 대해 validate 통과
  3) 금지 필드(raw_text 등) 포함 시 fail (additionalProperties:false = fail-closed)
  4) sha256 digest 형식(^sha256:[0-9a-f]{64}$) 위반 시 fail
  5) required 필드 누락 시 fail
  6) learning_event에 policy_approval 없으면 fail
  7) usage_log external_send_zero / raw_text_logged const 위반 시 fail
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

# tests/connect_loop/ -> repo_root
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "schemas" / "connect_loop"

SCHEMA_FILES = {
    "chat_request": "chat_request.schema.json",
    "router_decision": "router_decision.schema.json",
    "usage_log": "usage_log_v1_1.schema.json",
    "learning_event": "learning_event_v1.schema.json",
}


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_schema(key: str) -> dict:
    return json.loads((SCHEMA_DIR / SCHEMA_FILES[key]).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# 유효 샘플 4건
# --------------------------------------------------------------------------- #

VALID_CHAT_REQUEST = {
    "request_id": "req-0001",
    "session_id_digest": _digest("session-abc"),
    "tenant_id_digest": _digest("tenant-xyz"),
    "device_id": "device-001",
    "user_role": "employee",
    "department_id_digest": _digest("dept-finance"),
    "text_ref": "device_local_only",
    "text_digest": _digest("실제 사용자 입력 원문은 여기 없음"),
    "attachments": [
        {"content_digest": _digest("file-bytes"), "mime_type": "application/pdf", "size_bytes": 1024}
    ],
    "created_at": "2026-05-29T09:00:00Z",
    "schema_version": "chat_request.v1",
}

VALID_ROUTER_DECISION = {
    "request_id": "req-0001",
    "intent_label": "accounting_classify",
    "target_box_id": "5",
    "target_endpoint": "POST /accounting/classify",
    "routing_confidence": 0.92,
    "reason_code": "INTENT_KEYWORD_MATCH",
    "fallback_required": False,
    "policy_precheck": "allow",
    "schema_version": "router_decision.v1",
}

VALID_USAGE_LOG = {
    "log_id": "log-0001",
    "timestamp": "2026-05-29T09:00:01Z",
    "request_id": "req-0001",
    "device_id_digest": _digest("device-001"),
    "tenant_id_digest": _digest("tenant-xyz"),
    "department_id_digest": _digest("dept-finance"),
    "request_digest": _digest("요청내용"),
    "intent_label": "accounting_classify",
    "box_id": "5",
    "endpoint": "POST /accounting/classify",
    "routing_confidence": 0.92,
    "integration_mode": "real",
    "real_validation_done": True,
    "result_digest": _digest("결과"),
    "source_digests": [_digest("source-1"), _digest("source-2")],
    "policy_decision": "allow",
    "policy_reason_code": "OK",
    "latency_ms": 134.5,
    "external_send_zero": True,
    "raw_text_logged": False,
    "learning_candidate": True,
    "learning_event_created": False,
    "retention_class": "audit_digest_only",
    "created_by_component": "connect_loop.middleware",
    "schema_hash": _digest("usage_log.v1.1 schema body"),
    "schema_version": "usage_log.v1.1",
}

VALID_LEARNING_EVENT = {
    "learning_event_id": "le-0001",
    "source_usage_log_id": "log-0001",
    "created_at": "2026-05-29T10:00:00Z",
    "status": "APPROVED",
    "tenant_scope": "team",
    "learning_type": "accounting_classify",
    "raw_input_saved": False,
    "raw_output_saved": False,
    "approved_text_ref": "vault://approved/le-0001",
    "approved_text_digest": _digest("승인 정제 텍스트"),
    "sanitized_summary_digest": _digest("정제 요약"),
    "sanitized_summary_saved": False,
    "label": {
        "intent_label": "accounting_classify",
        "target_box_id": "5",
        "quality": "good",
    },
    "policy_approval": {
        "decision": "approved",
        "approver_role": "manager",
        "reason_code": "REVIEWED_OK",
    },
    "dlp_result": {
        "passed": True,
        "pii_detected": False,
        "secret_detected": False,
        "policy_violation": False,
    },
    "retention_days": 90,
    "expires_at": "2026-08-27T10:00:00Z",
    "verified_for_training": True,
    "schema_version": "learning_event.v1",
}

VALID_SAMPLES = {
    "chat_request": VALID_CHAT_REQUEST,
    "router_decision": VALID_ROUTER_DECISION,
    "usage_log": VALID_USAGE_LOG,
    "learning_event": VALID_LEARNING_EVENT,
}


# --------------------------------------------------------------------------- #
# 1) self-validate (draft-07 meta)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("key", sorted(SCHEMA_FILES))
def test_schema_self_validates_draft07(key):
    schema = load_schema(key)
    # draft-07 meta-schema 위반 시 SchemaError 발생
    Draft7Validator.check_schema(schema)
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["additionalProperties"] is False, "fail-closed: additionalProperties must be false"


# --------------------------------------------------------------------------- #
# 2) 유효 샘플 validate 통과
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("key", sorted(VALID_SAMPLES))
def test_valid_sample_passes(key):
    schema = load_schema(key)
    Draft7Validator(schema).validate(VALID_SAMPLES[key])


# --------------------------------------------------------------------------- #
# 3) 금지 필드 포함 시 fail (fail-closed)
# --------------------------------------------------------------------------- #

FORBIDDEN_FIELDS = [
    "raw_text",
    "raw_query",
    "raw_answer",
    "raw_source_text",
    "source_doc_name",
    "file_name",
    "absolute_local_path",
    "token",
    "password",
    "secret",
]


@pytest.mark.parametrize("key", sorted(VALID_SAMPLES))
@pytest.mark.parametrize("forbidden", FORBIDDEN_FIELDS)
def test_forbidden_field_fails(key, forbidden):
    schema = load_schema(key)
    sample = copy.deepcopy(VALID_SAMPLES[key])
    sample[forbidden] = "원문이라고-가정한-값"
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


# --------------------------------------------------------------------------- #
# 4) sha256 digest 형식 위반 시 fail
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "key,field",
    [
        ("chat_request", "text_digest"),
        ("chat_request", "session_id_digest"),
        ("usage_log", "request_digest"),
        ("usage_log", "schema_hash"),
        ("learning_event", "approved_text_digest"),
    ],
)
@pytest.mark.parametrize(
    "bad_value",
    [
        "not-a-digest",
        "sha256:TOOSHORT",
        "sha256:" + "g" * 64,  # non-hex
        "md5:" + "a" * 64,  # wrong algo prefix
        "a" * 64,  # missing prefix
    ],
)
def test_bad_digest_format_fails(key, field, bad_value):
    schema = load_schema(key)
    sample = copy.deepcopy(VALID_SAMPLES[key])
    sample[field] = bad_value
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_good_digest_format_passes():
    # 정상 digest는 통과해야 한다 (정규식 오버픽 방지)
    schema = load_schema("chat_request")
    sample = copy.deepcopy(VALID_CHAT_REQUEST)
    sample["text_digest"] = "sha256:" + "0" * 64
    Draft7Validator(schema).validate(sample)


# --------------------------------------------------------------------------- #
# 5) required 필드 누락 시 fail
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("key", sorted(VALID_SAMPLES))
def test_each_required_field_missing_fails(key):
    schema = load_schema(key)
    for field in schema["required"]:
        sample = copy.deepcopy(VALID_SAMPLES[key])
        del sample[field]
        with pytest.raises(ValidationError):
            Draft7Validator(schema).validate(sample)


# --------------------------------------------------------------------------- #
# 6) learning_event: policy_approval / dlp_result / retention_days 없으면 BLOCK
# --------------------------------------------------------------------------- #

def test_learning_event_without_policy_approval_fails():
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    del sample["policy_approval"]
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_learning_event_without_policy_decision_fails():
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    del sample["policy_approval"]["decision"]
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_learning_event_without_dlp_result_fails():
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    del sample["dlp_result"]
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_learning_event_without_retention_days_fails():
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    del sample["retention_days"]
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


@pytest.mark.parametrize("field", ["raw_input_saved", "raw_output_saved", "sanitized_summary_saved"])
def test_learning_event_raw_saved_true_blocked(field):
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    sample[field] = True  # const false 위반 -> BLOCK
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


# --------------------------------------------------------------------------- #
# 7) usage_log const 불변식 위반 시 fail
# --------------------------------------------------------------------------- #

def test_usage_log_external_send_zero_violation_fails():
    schema = load_schema("usage_log")
    sample = copy.deepcopy(VALID_USAGE_LOG)
    sample["external_send_zero"] = False  # const true 위반
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_usage_log_raw_text_logged_violation_fails():
    schema = load_schema("usage_log")
    sample = copy.deepcopy(VALID_USAGE_LOG)
    sample["raw_text_logged"] = True  # const false 위반
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_usage_log_retention_class_violation_fails():
    schema = load_schema("usage_log")
    sample = copy.deepcopy(VALID_USAGE_LOG)
    sample["retention_class"] = "training_data"  # const audit_digest_only 위반
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


# --------------------------------------------------------------------------- #
# 8) 실측 엔드포인트 enum 고정 확인 (코드에 없는 경로 금지)
# --------------------------------------------------------------------------- #

def test_router_endpoint_enum_matches_measured_routes():
    schema = load_schema("router_decision")
    enum = set(schema["properties"]["target_endpoint"]["enum"])
    measured = {
        "POST /v1/helpers/1/search",
        "POST /v1/cards/2/rewrite",
        "POST /v1/cards/3/draft",
        "POST /accounting/classify",
        "POST /v1/chat/completions",
        "none",
    }
    assert enum == measured


def test_text_ref_is_device_local_only_const():
    schema = load_schema("chat_request")
    assert schema["properties"]["text_ref"]["const"] == "device_local_only"
