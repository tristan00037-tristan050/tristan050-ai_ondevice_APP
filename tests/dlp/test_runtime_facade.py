import subprocess
import sys
from pathlib import Path

import pytest

from butler_pc_core.dlp import scan_reason_codes, scan_runtime


@pytest.mark.parametrize(
    "text,category,reason",
    [
        ("alice@example.com", "email", "PII_EMAIL"),
        ("900101-1234567", "korean_rrn", "PII_KOREAN_RRN"),
        ("010-1234-5678", "phone", "PII_PHONE"),
        ("1234-5678-9012-3456", "card_or_account", "PII_CARD_OR_ACCOUNT"),
        ("token: abcdefghijklmno", "secret", "SECRET"),
        ("/Users/person/private.txt", "local_path", "LOCAL_PATH"),
    ],
)
def test_runtime_facade_reports_raw_zero_category_evidence(text, category, reason):
    result = scan_runtime(text)

    assert result.any_detected is True
    assert category in {finding.category for finding in result.findings}
    assert reason in scan_reason_codes(text)
    assert all(not hasattr(finding, "matched_text") for finding in result.findings)


def test_reason_codes_keep_box3_legacy_order():
    text = "token: abcdefghijklmno alice@example.com 010-1234-5678"
    assert scan_reason_codes(text) == ["PII_EMAIL", "PII_PHONE", "SECRET"]


@pytest.mark.parametrize(
    "digest",
    [
        "sha256:" + "1234567890abcdef" * 4,
        "1234567890abcdef" * 4,
    ],
)
def test_sha256_digest_is_not_misclassified_as_pii(digest):
    assert scan_runtime(digest).any_detected is False


def test_normalized_only_is_true_for_zero_width_bypass():
    result = scan_runtime("alice\u200b@example.com")
    assert result.normalized_only is True
    assert result.findings[0].origin == "normalized"


def test_too_long_is_mapped_to_stable_box3_legacy_block_code():
    text = "x" * 200_001
    result = scan_runtime(text)
    assert result.too_long is True
    assert result.policy_violation is True
    assert result.findings == ()
    assert scan_reason_codes(text) == ["SECRET"]


@pytest.mark.parametrize(
    "text",
    [
        (("sha256:" + "a" * 64 + " ") * 4_000).strip(),
        (("b" * 64 + " ") * 4_000).strip(),
    ],
    ids=["canonical_sha", "bare_sha"],
)
def test_raw_length_limit_runs_before_digest_shielding(text):
    assert len(text) > 200_000
    result = scan_runtime(text)
    assert result.too_long is True
    assert result.policy_violation is True


@pytest.mark.parametrize(
    "text",
    [
        "보고일은 2026-07-04 12:30입니다.",
        "계약금액은 30,000,000원입니다.",
        "주소는 서울특별시 중구 세종대로 110입니다.",
        "일반 접수번호는 20260712입니다.",
    ],
)
def test_golden_business_text_is_not_newly_blocked_or_redacted(text):
    assert scan_runtime(text).any_detected is False


def test_missing_group_a_corpus_fails_with_fixed_raw_zero_code(tmp_path):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/eval/dlp_corpus_schema_probe.py"), str(tmp_path / "missing.jsonl")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stdout.splitlines() == ["DLP_CORPUS_SCHEMA_PROBE_OK=0", "ERROR_CODE=CORPUS_SCHEMA_UNKNOWN"]
    assert result.stderr == ""
