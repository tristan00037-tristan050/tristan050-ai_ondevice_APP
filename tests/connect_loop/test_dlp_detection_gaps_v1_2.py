from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from butler_pc_core.connect_loop.dlp_guard import assert_no_raw_or_secret_material, scan_runtime_text
from butler_pc_core.connect_loop.persisted_safety import PersistedSafetyViolation, _enforce_persisted_safety


@pytest.mark.parametrize(
    "text",
    [
        "입금 계좌 110-234-567890",
        "상환 계좌 110‐234‐567890",
        "예금 대체 110–234–567890",
        "계좌번호 110－234－567890",
    ],
    ids=["ascii_hyphen", "unicode_hyphen", "en_dash", "fullwidth_hyphen"],
)
def test_dlp_hyphenated_account_variants_are_pii(text: str) -> None:
    result = scan_runtime_text(text)

    assert result == {
        "passed": False,
        "pii_detected": True,
        "secret_detected": False,
        "policy_violation": False,
    }
    assert text not in str(result)


@pytest.mark.parametrize(
    "text",
    [
        "보고일은 2026-07-04입니다",
        "분석 기간 2026-07-04 ~ 2026-07-31",
        "접수번호 02-1234-5678은 전화번호로 별도 PII 처리됩니다",
    ],
    ids=["date", "period", "phone_is_existing_pii_not_account"],
)
def test_dlp_dates_are_not_promoted_to_account_false_positive(text: str) -> None:
    result = scan_runtime_text(text)

    if "02-1234-5678" in text:
        assert result["pii_detected"] is True
        assert result["passed"] is False
    else:
        assert result == {
            "passed": True,
            "pii_detected": False,
            "secret_detected": False,
            "policy_violation": False,
        }


@pytest.mark.parametrize(
    "text",
    [
        "비밀번호는 1234야",
        "비번: abcd1234",
        "암호 -> P@ssw0rd",
        "비밀번호는 `a1b2c3`",
        "비밀번호는 정책1234야",
        "비번: 관리자1234",
    ],
    ids=[
        "spoken_password_digit",
        "short_pw_colon",
        "arrow_symbol_secret",
        "quoted_secret",
        "safe_word_prefixed_secret",
        "admin_prefixed_secret",
    ],
)
def test_dlp_ko_spoken_secret_is_secret(text: str) -> None:
    result = scan_runtime_text(text)

    assert result["passed"] is False
    assert result["secret_detected"] is True
    assert text not in str(result)


@pytest.mark.parametrize(
    "text",
    [
        "비밀번호 정책을 변경합니다",
        "비밀번호 변경 주기를 안내합니다",
        "암호화 논의는 별도 보안 문서에서 다룹니다",
        "비번 재설정 절차를 설명합니다",
    ],
    ids=["password_policy", "password_rotation", "encryption_discussion", "password_reset_process"],
)
def test_dlp_ko_policy_sentences_are_safe(text: str) -> None:
    result = scan_runtime_text(text)

    assert result == {
        "passed": True,
        "pii_detected": False,
        "secret_detected": False,
        "policy_violation": False,
    }


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("user@example.com", "pii_detected"),
        ("010-1234-5678", "pii_detected"),
        ("900101-1234567", "pii_detected"),
        ("4111 1111 1111 1111", "pii_detected"),
        ("token=abcd1234567890", "secret_detected"),
        ("AKIA1234567890ABCDEF", "secret_detected"),
        ("sk-abcdef1234567890", "secret_detected"),
        ("/Users/example/Desktop/file.docx", "policy_violation"),
    ],
    ids=["email", "phone", "rrn", "card", "token", "aws_key", "openai_key", "local_path"],
)
def test_existing_dlp_patterns_keep_detecting(text: str, field: str) -> None:
    result = scan_runtime_text(text)

    assert result["passed"] is False
    assert result[field] is True
    assert text not in str(result)


@pytest.mark.parametrize(
    "value",
    [
        "입금 계좌 110-234-567890",
        "상환 계좌 110‐234‐567890",
        "비밀번호는 1234야",
        "비번: abcd1234",
    ],
    ids=[
        "shadow_047_ascii_account",
        "shadow_054_unicode_account",
        "shadow_078_spoken_pw",
        "pii_009_short_pw",
    ],
)
def test_group_a_gap_cases_fail_closed_in_persisted_safety(value: str) -> None:
    with pytest.raises(PersistedSafetyViolation, match="PERSISTED_SCALAR_DLP_BLOCK"):
        _enforce_persisted_safety({"approved_text_ref": value})


@pytest.mark.parametrize(
    "value",
    [
        "비밀번호는 정책1234야",
        "비번: 관리자1234",
    ],
    ids=["policy_prefixed_secret", "admin_prefixed_secret"],
)
def test_safe_word_prefixed_secret_values_still_fail_closed(value: str) -> None:
    with pytest.raises(PersistedSafetyViolation, match="PERSISTED_SCALAR_DLP_BLOCK"):
        _enforce_persisted_safety({"approved_text_ref": value})


def test_assert_no_raw_or_secret_material_maps_gap_to_fixed_code() -> None:
    try:
        assert_no_raw_or_secret_material({"digest_only_note": "비밀번호는 1234야"})
    except ValueError as exc:
        assert str(exc) == "RAW_OR_SECRET_VALUE_FORBIDDEN"
    else:  # pragma: no cover
        raise AssertionError("spoken secret scalar was not blocked")


def test_dlp_hyphen_helper_linear_time() -> None:
    payload = ("업무-검토-정책-안내 " * 700).strip()
    start = time.perf_counter()

    result = scan_runtime_text(payload)

    elapsed = time.perf_counter() - start
    assert elapsed < 1.0
    assert result["passed"] is True
    assert result["pii_detected"] is False


def test_dlp_verifier_parse_errors_are_fixed_code_only(tmp_path: Path) -> None:
    root = tmp_path
    source = root / "butler_pc_core" / "connect_loop" / "persisted_safety.py"
    tests = root / "tests" / "connect_loop" / "test_dlp_detection_gaps_v1_2.py"
    source.parent.mkdir(parents=True)
    tests.parent.mkdir(parents=True)
    source.write_text(
        "\n".join(
            [
                "import unicodedata",
                "# _HYPHEN_CHARS _ACCOUNT_HYPHEN_RE _has_hyphenated_account",
                "# _KO_SECRET_RE _KO_SECRET_SAFE_START _has_ko_secret_signal _has_ko_secret",
                '# unicodedata.normalize("NFKC", value)',
                "# _CARD_OR_ACCOUNT_RE.search(scan_value)",
                "# _has_hyphenated_account(scan_value)",
                "# _SECRET_RE.search(scan_value) or _has_ko_secret(scan_value)",
                r'_CARD_OR_ACCOUNT_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")',
                r"_SECRET_RE = re.compile(",
                r'    r"sk-[a-z0-9][a-z0-9._-]{10,})"',
                "def broken(:",
            ]
        ),
        encoding="utf-8",
    )
    tests.write_text(
        "\n".join(
            [
                "110-234-567890",
                "110‐234‐567890",
                "2026-07-04",
                "비밀번호는 1234야",
                "비밀번호는 정책1234야",
                "비번: 관리자1234",
                "비밀번호 정책을 변경합니다",
                "test_existing_dlp_patterns_keep_detecting",
                "test_dlp_hyphen_helper_linear_time",
                "RAW_OR_SECRET_VALUE_FORBIDDEN",
            ]
        ),
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "verify_dlp_detection_gaps_v1_2.py"), str(root)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert result.stdout.splitlines() == ["DLP_GAP_PATCH_OK=0", "ERROR_CODE=SOURCE_PARSE_ERROR"]
    assert result.stderr == ""
