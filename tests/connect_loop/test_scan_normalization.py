from __future__ import annotations

import pytest

from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text
from butler_pc_core.connect_loop.persisted_safety import _dlp_scan_all
from butler_pc_core.connect_loop.scan_normalization import (
    DLP_DETECTED_NORMALIZED_VARIANT,
    DLP_DETECTED_RAW,
    SCAN_INPUT_TOO_LONG,
    detect_any,
    scan_variants,
)


def _scan(value: str):
    return scan_runtime_text(value)


@pytest.mark.parametrize(
    "value",
    [
        "110-234-567890",
        "110‐234‐567890",
        "110–234–567890",
        "1️⃣1️⃣0️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣8️⃣9️⃣0️⃣",
        "1\u20e31\u20e30\u20e32\u20e33\u20e34\u20e35\u20e36\u20e37\u20e38\u20e39\u20e30\u20e3",
        "1\u03051\u03050\u03052\u03053\u03054\u03055\u03056\u03057\u03058\u03059\u03050\u0305",
        "１１０２３４５６７８９０",
        "일일공이삼사오육칠팔구영",
        "110:234:567890",
    ],
)
def test_account_variants_detected(value: str):
    assert _scan(value)["pii_detected"] is True
    assert _scan(value)["passed"] is False


@pytest.mark.parametrize(
    "value",
    [
        "홍길동 800101-1234567",
        "010-1234-5678",
        "02-123-4567",
        "test@example.com",
        "4111 1111 1111 1111",
    ],
)
def test_standard_patterns_still_detect(value: str):
    assert _scan(value)["passed"] is False


@pytest.mark.parametrize(
    "value",
    [
        "회의는 2026-07-04에 진행합니다.",
        "기간은 2026-07-04부터 2026-07-08까지입니다.",
        "시간은 2:30으로 조정합니다.",
        "비밀번호 정책 변경 안내입니다.",
        "사오정 프로젝트 일정 공유",
        "삼성전자 계좌이체 안내 문서 제목",
        "암호화 논의 안건",
        "전화 회의록 초안",
    ],
)
def test_false_positive_controls(value: str):
    assert _scan(value)["passed"] is True


@pytest.mark.parametrize("value", ["비밀번호는 1234야", "비번: abcd1234", "암호는 a!2"])
def test_korean_secret_variants_detected(value: str):
    assert _scan(value)["secret_detected"] is True
    assert _scan(value)["passed"] is False


def test_variant_reason_codes_do_not_echo_raw_values():
    result = detect_any({"digits": r"\d{12}"}, "1️⃣1️⃣0️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣8️⃣9️⃣0️⃣")
    assert result.detected is True
    assert result.reason_code == DLP_DETECTED_NORMALIZED_VARIANT
    assert result.variant_id != "v0_raw"
    assert result.pattern_id == "digits"
    assert "110" not in str(result)


def test_raw_reason_code_for_raw_hit():
    result = detect_any({"digits": r"\d{12}"}, "110234567890")
    assert result.reason_code == DLP_DETECTED_RAW
    assert result.variant_id == "v0_raw"


def test_scan_input_too_long_fail_safe():
    result = detect_any({"never": r"never"}, "가" * 200_001)
    assert result.detected is True
    assert result.too_long is True
    assert result.reason_code == SCAN_INPUT_TOO_LONG
    scan = _dlp_scan_all("가" * 200_001)
    assert scan.policy_violation is True
    assert scan.scan_too_long is True


def test_scan_variants_dedup_no_duplicate_texts():
    variants = scan_variants("010-1234-5678")
    assert len({item.text for item in variants}) == len(variants)
