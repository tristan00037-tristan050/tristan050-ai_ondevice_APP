from butler_pc_core.dlp import SAFE_SECRET_REPLACEMENT, redact_fail_closed, scan_runtime


def test_safe_raw_email_span_is_partially_redacted_and_rescanned():
    result = redact_fail_closed("담당자: alice@example.com")
    assert result == "담당자: " + SAFE_SECRET_REPLACEMENT
    assert scan_runtime(result).any_detected is False


def test_normalized_only_hit_forces_full_scalar_replacement():
    assert redact_fail_closed("담당자: alice\u200b@example.com") == SAFE_SECRET_REPLACEMENT


def test_callable_context_hit_forces_full_scalar_replacement():
    assert redact_fail_closed("계좌 110 234 567890") == SAFE_SECRET_REPLACEMENT


def test_secret_and_local_path_force_full_scalar_replacement():
    assert redact_fail_closed("token: abcdefghijklmno") == SAFE_SECRET_REPLACEMENT
    assert redact_fail_closed("첨부: /Users/person/private.txt") == SAFE_SECRET_REPLACEMENT


def test_all_box6_secret_label_and_private_key_forms_fail_closed():
    for text in (
        "client secret: abcdef123456",
        "access key: abcdef123456",
        "auth key: abcdef123456",
        "seed phrase: correct horse battery staple",
        "-----BEGIN PRIVATE KEY-----",
    ):
        assert redact_fail_closed(text) == SAFE_SECRET_REPLACEMENT


def test_no_hit_is_byte_identical():
    text = "정상 검토 결과입니다."
    assert redact_fail_closed(text) == text


def test_too_long_input_fails_closed():
    assert redact_fail_closed("가" * 200_001) == SAFE_SECRET_REPLACEMENT
