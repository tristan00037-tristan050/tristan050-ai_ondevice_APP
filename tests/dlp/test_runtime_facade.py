from __future__ import annotations

import pytest

from butler_pc_core.dlp.runtime import scan_reason_codes, scan_runtime


def test_legacy_reason_order_stable():
    value = "메일 user@example.com 전화 010-1234-5678 password: abcdef123456"
    assert scan_reason_codes(value) == ["PII_EMAIL", "PII_PHONE", "SECRET"]


@pytest.mark.parametrize(
    "value,category",
    [
        ("메일 user@example.com", "email"),
        ("전화 010-1234-5678", "phone"),
        ("주민 900101-1234567", "korean_rrn"),
        ("카드 4111 1111 1111 1111", "card_or_account"),
        ("password: abcdef123456", "secret"),
        ("/Users/test/private.docx", "local_path"),
    ],
)
def test_standard_categories(value: str, category: str):
    result = scan_runtime(value)
    assert result.any_detected
    assert category in {item.category for item in result.findings}
    assert value not in repr(result)


@pytest.mark.parametrize(
    "value",
    [
        "계좌 110:234:567890",
        "카드 ４１１１ １１１１ １１１１ １１１１",
        "전화 0️⃣1️⃣0️⃣-1️⃣2️⃣3️⃣4️⃣-5️⃣6️⃣7️⃣8️⃣",
        "주민 구영영일영일-일이삼사오육칠",
    ],
)
def test_normalized_mutations_detected(value: str):
    result = scan_runtime(value)
    assert result.pii_detected
    if "４" not in value:
        assert any(item.origin == "normalized" for item in result.findings)


def test_sha256_formats_are_shielded():
    canonical = "sha256:" + "a" * 64
    bare = "b" * 64
    assert not scan_runtime(canonical).any_detected
    assert not scan_runtime(bare).any_detected
    assert not scan_runtime(f"digest={canonical} other={bare}").any_detected


@pytest.mark.parametrize(
    "value",
    [
        "회의는 2026-07-04에 진행합니다.",
        "시간은 2:30입니다.",
        "금액은 4억 원입니다.",
        "주소는 서울시 강남구 테헤란로입니다.",
        "삼성전자 계좌이체 안내 문서 제목",
    ],
)
def test_golden_negatives(value: str):
    assert not scan_runtime(value).any_detected


def test_too_long_fail_closed():
    result = scan_runtime("가" * 200_001)
    assert result.too_long
    assert result.policy_violation
    assert scan_reason_codes("가" * 200_001) == ["LOCAL_PATH"]
