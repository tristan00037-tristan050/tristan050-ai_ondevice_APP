from __future__ import annotations

from pathlib import Path

import pytest

from butler_pc_core.connect_loop.attachment_features import RuntimeAttachment, extract_attachment_features
from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text
from butler_pc_core.connect_loop.intake_router import decide_intake
from butler_pc_core.connect_loop.learning_candidate_gate import (
    ApprovedRefBundle,
    build_learning_gate_input,
    create_learning_event_result,
    select_learning_candidates,
)
from butler_pc_core.connect_loop.persisted_safety import PersistedSafetyViolation, _PII_PATTERNS, _enforce_persisted_safety
from butler_pc_core.connect_loop.scan_normalization import SCAN_INPUT_TOO_LONG, detect_any, scan_variants


KEYCAP = {"0": "0️⃣", "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣", "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣"}
FULLWIDTH = str.maketrans("0123456789", "０１２３４５６７８９")
ARABIC_INDIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
KOREAN_DIGITS = str.maketrans({"0": "공", "1": "일", "2": "이", "3": "삼", "4": "사", "5": "오", "6": "육", "7": "칠", "8": "팔", "9": "구"})


def _keycap(value: str) -> str:
    return "".join(KEYCAP.get(char, char) for char in value)


def _combining(value: str) -> str:
    return "".join(char + "\u0301" if char.isdigit() else char for char in value)


VARIANT_BUILDERS = (
    ("raw", lambda value: value),
    ("zero_width", lambda value: value.replace("-", "\u200b-").replace(" ", "\u200b ")),
    ("keycap", _keycap),
    ("fullwidth", lambda value: value.translate(FULLWIDTH)),
    ("arabic_indic", lambda value: value.translate(ARABIC_INDIC)),
    ("colon", lambda value: value.replace("-", ":").replace(" ", ":")),
    ("unicode_hyphen", lambda value: value.replace("-", "‐").replace(" ", "‐")),
    ("korean_digits", lambda value: value.translate(KOREAN_DIGITS)),
    ("combining_mark", _combining),
)

SENSITIVE_BASES = {
    "account": "110-234-567890",
    "card": "4111 1111 1111 1111",
    "phone": "010-1234-5678",
    "rrn": "900101-1234567",
}


@pytest.mark.parametrize(
    ("sensitive_class", "variant_id", "text"),
    [
        (sensitive_class, variant_id, f"{sensitive_class} {builder(base)}")
        for sensitive_class, base in SENSITIVE_BASES.items()
        for variant_id, builder in VARIANT_BUILDERS
    ],
)
def test_group_a_36_variants_are_all_detected(sensitive_class: str, variant_id: str, text: str) -> None:
    result = scan_runtime_text(text)

    assert result["passed"] is False, (sensitive_class, variant_id)
    assert result["pii_detected"] is True
    assert text not in repr(result)


@pytest.mark.parametrize(
    "text",
    [
        "계좌 110-234-567890",
        "계좌 003-12-456789",
        "카드 4111 1111 1111 1111",
        "카드 5555-5555-5555-4444",
        "전화 010-1234-5678",
        "전화 +82 10-1234-5678",
        "주민 900101-1234567",
        "메일 user@example.com",
    ],
)
def test_standard_sensitive_forms_keep_detecting(text: str) -> None:
    assert scan_runtime_text(text)["passed"] is False


@pytest.mark.parametrize(
    "text",
    [
        "삼성전자 계좌이체 안내 문구만 검토합니다",
        "이사 일정은 다음 주 화요일입니다",
        "보고일은 2026-07-04입니다",
        "회의 시간은 2:30입니다",
        "사오정 프로젝트 킥오프 자료입니다",
        "계좌라는 단어만 있고 숫자는 없습니다",
        "카드 디자인 시안을 검토합니다",
        "주민 의견 수렴 회의록입니다",
        # 리뷰 P2: 계좌 문맥 + 무관한 날짜·시각이 공백 경계를 넘어 하나의 긴 숫자열로
        # 병합되어 계좌번호로 오탐되면 안 된다.
        "계좌 양식 검토. 보고일은 2026-07-04 12:30입니다",
    ],
)
def test_false_positive_control_group_passes(text: str) -> None:
    assert scan_runtime_text(text) == {
        "passed": True,
        "pii_detected": False,
        "secret_detected": False,
        "policy_violation": False,
    }


def test_scan_input_too_long_is_fail_closed_without_text_echo() -> None:
    payload = "안전문장" * 50_001
    result = detect_any({"never": lambda _text: False}, payload, max_scan_chars=200_000)

    assert result.detected is True
    assert result.too_long is True
    assert result.reason_code == SCAN_INPUT_TOO_LONG
    assert payload not in repr(result)
    assert scan_runtime_text(payload)["passed"] is False
    assert scan_runtime_text(payload)["policy_violation"] is True


def test_scan_variants_are_deduplicated() -> None:
    variants = scan_variants("plainsafetext")

    assert [variant.variant_id for variant in variants] == ["v0_raw"]


def test_separator_normalization_preserves_whitespace_boundaries() -> None:
    # 리뷰 P2: 공백으로 분리된 무관한 필드는 하나의 숫자열로 병합되지 않는다.
    v4 = [v.text for v in scan_variants("2026-07-04 12:30") if v.variant_id == "v4_separators_removed"]
    assert v4 == ["20260704 1230"]
    # 반면 토큰 내부 구분자 위장 계좌는 그대로 붙어 탐지 가능해야 한다.
    v4_acct = [v.text for v in scan_variants("123-456-7890") if v.variant_id == "v4_separators_removed"]
    assert v4_acct and "1234567890" in v4_acct[0]


def test_verifier_failure_path_emits_only_fixed_keys() -> None:
    # 리뷰 P1: 검증기 실패 경로가 pytest 원문(샘플·traceback·긴 덤프)을 stdout 으로 흘리면 안 된다.
    source = (Path(__file__).resolve().parents[2] / "scripts" / "verify_dlp_scan_normalization.py").read_text(encoding="utf-8")
    assert "print(result.stdout" not in source
    assert "result.stdout" not in source


def test_normalized_only_result_exposes_ids_not_text() -> None:
    result = detect_any({"compact": lambda text: "110234567890" in text}, "계좌 110:234:567890")

    assert result.detected is True
    assert result.reason_code == "DLP_DETECTED_NORMALIZED_VARIANT"
    assert result.variant_id == "v4_separators_removed"
    assert result.pattern_id == "compact"
    assert "110234567890" not in repr(result)


def test_dlp_scan_result_repr_has_no_raw() -> None:
    payload = "계좌 110-234-567890 API키 sk-abcdef123456"
    result = detect_any(_PII_PATTERNS, payload)
    rendered = repr(result) + str(result)

    assert result.detected is True
    assert "110" not in rendered
    assert "sk-" not in rendered
    assert "567890" not in rendered
    assert result.variant_id is not None


def test_pytest_assertion_message_has_no_raw() -> None:
    payload = "주민 900101-1234567"
    result = detect_any(_PII_PATTERNS, payload)
    safe_message = f"variant={result.variant_id} pattern={result.pattern_id}"

    assert payload not in safe_message
    assert "900101" not in safe_message
    assert result.detected, safe_message


def test_persisted_safety_blocks_normalized_only_value() -> None:
    with pytest.raises(PersistedSafetyViolation, match="PERSISTED_SCALAR_DLP_BLOCK"):
        _enforce_persisted_safety({"approved_text_ref": "계좌 110:234:567890"})


def test_attachment_features_records_dlp_bucket_without_raw_value() -> None:
    text = "첨부 안내 계좌 " + _keycap("110-234-567890")
    bundle = extract_attachment_features([RuntimeAttachment(text.encode("utf-8"), filename="memo.txt", content_type="text/plain")])
    encoded = repr(bundle.to_dict())

    assert "DLP_SIGNAL_PRESENT" in encoded
    assert text not in encoded
    assert "110-234-567890" not in encoded


def test_intake_blocks_attachment_with_normalized_only_dlp_signal() -> None:
    text = "첨부 안내 계좌 " + _keycap("110:234:567890")
    bundle = extract_attachment_features([RuntimeAttachment(text.encode("utf-8"), filename="memo.txt", content_type="text/plain")])
    decision = decide_intake(request_id="req-dlp-block", attachment_bundle=bundle, policy_ready_override=True)
    encoded = repr(decision)

    assert decision["target_endpoint"] == "none"
    assert decision["fail_class"] == "INTAKE_DLP_SIGNAL_BLOCKED"
    assert decision["next_action"] == "BLOCK"
    assert "DLP_SIGNAL_PRESENT" in encoded
    assert text not in encoded


def _digest(value: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _usage_log() -> dict:
    return {
        "log_id": "ulog-dlp-normalized-001",
        "timestamp": "2026-07-09T00:00:00Z",
        "request_id": "req-dlp-normalized-001",
        "device_id_digest": _digest("device"),
        "tenant_id_digest": _digest("tenant"),
        "department_id_digest": _digest("department"),
        "request_digest": _digest("request"),
        "intent_label": "memory_search",
        "box_id": "helper1",
        "endpoint": "POST /v1/helpers/1/search",
        "routing_confidence": 0.93,
        "integration_mode": "real",
        "real_validation_done": True,
        "result_digest": _digest("result"),
        "source_digests": [_digest("source")],
        "policy_decision": "allow",
        "policy_reason_code": "OK",
        "latency_ms": 12.5,
        "external_send_zero": True,
        "raw_text_logged": False,
        "learning_candidate": True,
        "learning_event_created": False,
        "retention_class": "audit_digest_only",
        "created_by_component": "connect_loop.usage_accumulator",
        "schema_hash": _digest("usage_log_schema"),
        "schema_version": "usage_log.v1.1",
    }


def test_learning_candidate_gate_drops_normalized_only_dlp_hit() -> None:
    candidate = select_learning_candidates([_usage_log()])[0]
    gate_input = build_learning_gate_input(
        candidate,
        ApprovedRefBundle(
            approved_text_ref="vault://learning-events/dlp-normalized-001",
            approved_text_digest=_digest("approved"),
            sanitized_summary_digest=_digest("summary"),
            runtime_text_for_dlp="계좌 110:234:567890",
        ),
        {
            "learning_allowed": True,
            "tenant_scope": "device",
            "retention_days": 30,
            "expires_at": "2026-12-31T00:00:00Z",
            "reason_code": "LEARNING_ALLOWED_SANITIZED",
        },
    )
    result = create_learning_event_result(gate_input)

    assert result.event is None
    assert result.drop_reason == "DLP_FAILED"
    assert "110:234:567890" not in repr(gate_input["dlp_runtime_scan"])


def test_verifier_script_exists() -> None:
    assert Path("scripts/verify_dlp_scan_normalization.py").exists()
