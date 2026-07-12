from __future__ import annotations

import pytest

from butler_pc_core.dlp.runtime import SAFE_SECRET_REPLACEMENT, redact_fail_closed, scan_runtime


def test_no_hit_byte_identical():
    value = "정상 문서 문장입니다."
    assert redact_fail_closed(value) == value


def test_raw_email_can_be_partially_redacted_and_residual_zero():
    result = redact_fail_closed("담당자: user@example.com 확인")
    assert result == f"담당자: {SAFE_SECRET_REPLACEMENT} 확인"
    assert not scan_runtime(result).any_detected


@pytest.mark.parametrize(
    "value",
    [
        "계좌 110:234:567890",
        "전화 0️⃣1️⃣0️⃣-1️⃣2️⃣3️⃣4️⃣-5️⃣6️⃣7️⃣8️⃣",
        "비밀번호: abcdef123456",
        "/Users/test/private.docx",
    ],
)
def test_normalized_callable_secret_path_full_scalar(value: str):
    assert redact_fail_closed(value) == SAFE_SECRET_REPLACEMENT


def test_raw_rrn_partial_and_digest_not_redacted():
    digest = "sha256:" + "a" * 64
    value = f"주민 900101-1234567 evidence={digest}"
    result = redact_fail_closed(value)
    assert SAFE_SECRET_REPLACEMENT in result
    assert digest in result
    assert not scan_runtime(result).any_detected


def test_too_long_full_scalar():
    assert redact_fail_closed("가" * 200_001) == SAFE_SECRET_REPLACEMENT
