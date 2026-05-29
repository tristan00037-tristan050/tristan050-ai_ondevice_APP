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

# --------------------------------------------------------------------------- #
# 9) const 위반 negative (schema_version, text_ref)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("key", sorted(VALID_SAMPLES))
def test_schema_version_const_violation_fails(key):
    schema = load_schema(key)
    sample = copy.deepcopy(VALID_SAMPLES[key])
    sample["schema_version"] = "wrong.version.v9"
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_chat_request_text_ref_const_violation_fails():
    schema = load_schema("chat_request")
    sample = copy.deepcopy(VALID_CHAT_REQUEST)
    sample["text_ref"] = "server_copy"  # const device_local_only 위반
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


# --------------------------------------------------------------------------- #
# 10) enum / 수치 경계 위반 negative
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "key,field,bad",
    [
        ("router_decision", "intent_label", "delete_everything"),
        ("router_decision", "target_box_id", "99"),
        ("router_decision", "target_endpoint", "POST /v1/cards/4/review"),
        ("router_decision", "policy_precheck", "maybe"),
        ("usage_log", "integration_mode", "mock"),
        ("usage_log", "policy_decision", "perhaps"),
        ("learning_event", "status", "MAYBE"),
        ("learning_event", "tenant_scope", "galaxy"),
        ("learning_event", "learning_type", "telepathy"),
    ],
)
def test_enum_violation_fails(key, field, bad):
    schema = load_schema(key)
    sample = copy.deepcopy(VALID_SAMPLES[key])
    sample[field] = bad
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


@pytest.mark.parametrize(
    "key,field,bad",
    [
        ("router_decision", "routing_confidence", 1.5),
        ("router_decision", "routing_confidence", -0.1),
        ("usage_log", "routing_confidence", 2),
        ("usage_log", "latency_ms", -5),
        ("learning_event", "retention_days", 0),
        ("learning_event", "retention_days", -30),
    ],
)
def test_numeric_boundary_violation_fails(key, field, bad):
    schema = load_schema(key)
    sample = copy.deepcopy(VALID_SAMPLES[key])
    sample[field] = bad
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


# --------------------------------------------------------------------------- #
# 11) RFC3339 date-time pattern (format 미검증 환경에서도 pattern 으로 강제)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "key,field",
    [
        ("chat_request", "created_at"),
        ("usage_log", "timestamp"),
        ("learning_event", "created_at"),
        ("learning_event", "expires_at"),
    ],
)
@pytest.mark.parametrize("bad", ["THIS-IS-NOT-A-DATE", "2026-13-40", "2026/05/29 09:00", "29-05-2026T09:00:00Z"])
def test_datetime_pattern_violation_fails(key, field, bad):
    schema = load_schema(key)
    sample = copy.deepcopy(VALID_SAMPLES[key])
    sample[field] = bad
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


# --------------------------------------------------------------------------- #
# 12) reason_code / 참조 필드 형식 위반 (원문 밀반입 채널 차단)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "key,field",
    [
        ("router_decision", "reason_code"),
        ("usage_log", "policy_reason_code"),
    ],
)
def test_reason_code_freetext_blocked(key, field):
    schema = load_schema(key)
    sample = copy.deepcopy(VALID_SAMPLES[key])
    sample[field] = "사용자가 입력한 자유 원문 문장입니다"  # 코드 형식 위반
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_learning_event_approved_text_ref_must_be_reference():
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    sample["approved_text_ref"] = "이건 그냥 원문 평문 텍스트"  # scheme:// 아님
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


# --------------------------------------------------------------------------- #
# 13) learning_event 분리 원칙 강제: APPROVED 면 정책 approved + DLP passed 필수
# --------------------------------------------------------------------------- #

def test_learning_event_approved_requires_policy_approved():
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    sample["status"] = "APPROVED"
    sample["policy_approval"]["decision"] = "rejected"  # APPROVED 인데 미승인 -> BLOCK
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_learning_event_approved_requires_dlp_passed():
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    sample["status"] = "APPROVED"
    sample["dlp_result"]["passed"] = False  # APPROVED 인데 DLP 실패 -> BLOCK
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


@pytest.mark.parametrize("flag", ["pii_detected", "secret_detected", "policy_violation"])
def test_learning_event_approved_blocks_dlp_detection(flag):
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    sample["status"] = "APPROVED"
    sample["dlp_result"][flag] = True  # APPROVED 인데 PII/secret/위반 검출 -> BLOCK
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


def test_learning_event_candidate_allows_pending_review():
    # CANDIDATE 상태는 최종 학습 투입 전(verified=false)이라면 정책/DLP 가 아직 미완료여도 통과한다.
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    sample["status"] = "CANDIDATE"
    sample["verified_for_training"] = False
    sample["policy_approval"]["decision"] = "needs_review"
    sample["dlp_result"]["passed"] = False
    Draft7Validator(schema).validate(sample)


def test_learning_event_verified_training_requires_approved_gate():
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    sample["status"] = "CANDIDATE"
    sample["verified_for_training"] = True
    sample["policy_approval"]["decision"] = "needs_review"
    sample["dlp_result"]["passed"] = False
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


@pytest.mark.parametrize("flag", ["pii_detected", "secret_detected", "policy_violation"])
def test_learning_event_verified_training_blocks_dlp_detection(flag):
    schema = load_schema("learning_event")
    sample = copy.deepcopy(VALID_LEARNING_EVENT)
    sample["verified_for_training"] = True
    sample["dlp_result"][flag] = True
    with pytest.raises(ValidationError):
        Draft7Validator(schema).validate(sample)


# SSOT §3 실측표가 단언하는 (엔드포인트 -> source file) 매핑.
# 테스트는 이 경로 문자열이 실제 sidecar 소스에 존재하는지 grep 한다(토톨로지 방지).
MEASURED_ENDPOINT_SOURCES = {
    "POST /v1/helpers/1/search": "butler_pc_core/sidecar/routes/helper1_search.py",
    "POST /v1/cards/2/rewrite": "butler_pc_core/sidecar/routes/box2_rewrite.py",
    "POST /v1/cards/3/draft": "butler_pc_core/sidecar/routes/box3_draft.py",
    "POST /accounting/classify": "butler_sidecar.py",
    # POST /v1/chat/completions 제거 (Codex P1, 2026-05-27): chat 라우터는 sidecar
    # (butler_sidecar.py)에 include_router되지 않음 — serving server 별도 제공.
    # 따라서 '실측 sidecar 엔드포인트' enum에서 제외, general_chat은 fallback 처리.
}


def test_router_endpoint_enum_matches_measured_set():
    # 1) enum 이 §3 실측 집합과 정확히 일치하는지 (+ unknown 의 'none').
    schema = load_schema("router_decision")
    enum = set(schema["properties"]["target_endpoint"]["enum"])
    assert enum == set(MEASURED_ENDPOINT_SOURCES) | {"none"}


def test_router_endpoint_paths_exist_in_sidecar_source():
    # 2) 토톨로지 방지: enum 의 각 경로가 실제 sidecar 소스 코드에 존재하는지 grep.
    #    (계약 PR 단독 체크아웃 등으로 sidecar 소스가 없으면 skip — 거짓 통과 대신 명시적 skip.)
    missing_sources = [
        src for src in MEASURED_ENDPOINT_SOURCES.values()
        if not (REPO_ROOT / src).exists()
    ]
    if missing_sources:
        pytest.skip(f"sidecar source not present in this checkout: {missing_sources}")

    for endpoint, src in MEASURED_ENDPOINT_SOURCES.items():
        path_only = endpoint.split(" ", 1)[1]  # 'POST /x' -> '/x'
        text = (REPO_ROOT / src).read_text(encoding="utf-8")
        assert f'"{path_only}"' in text or f"'{path_only}'" in text, (
            f"실측 단언 위반: {endpoint} 경로가 {src} 에 존재하지 않음 (SSOT §3 환각 의심)"
        )


def test_text_ref_is_device_local_only_const():
    schema = load_schema("chat_request")
    assert schema["properties"]["text_ref"]["const"] == "device_local_only"
