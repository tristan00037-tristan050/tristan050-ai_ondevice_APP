import subprocess
import sys
from pathlib import Path

import pytest

from butler_pc_core.cards.box3.security import Box3SecurityError, assert_runtime_text_safe
from butler_pc_core.connect_loop.dlp_guard import scan_runtime_text
from butler_pc_core.dlp import SAFE_SECRET_REPLACEMENT, redact_fail_closed, scan_reason_codes, scan_runtime


def test_adversarial_too_long_box3_and_guard_fail_closed():
    text = "x" * 200_001
    assert scan_reason_codes(text) == ["SECRET"]
    with pytest.raises(Box3SecurityError):
        assert_runtime_text_safe(text)
    assert scan_runtime_text(text) == {
        "passed": False,
        "pii_detected": False,
        "secret_detected": False,
        "policy_violation": True,
    }


def test_adversarial_digest_shielding_cannot_reduce_length_before_limit():
    text = (("sha256:" + "a" * 64 + " ") * 4_000).strip()
    assert len(text) == 287_999
    result = scan_runtime(text)
    assert result.too_long is True
    assert result.policy_violation is True


def test_adversarial_unsafe_replacement_output_zero():
    unsafe = "token: abcdefghijklmno1"
    result = redact_fail_closed("alice@example.com", replacement=unsafe)
    assert result == SAFE_SECRET_REPLACEMENT
    assert unsafe not in result


def test_dynamic_verifier_reports_all_adversarial_gates_safe():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/verify_dlp_runtime_unification.py")],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    lines = set(result.stdout.splitlines())
    assert "DLP_RUNTIME_UNIFICATION_VERIFY=1" in lines
    assert "DLP_TOO_LONG_BOX3_BLOCK=1" in lines
    assert "DLP_RAW_LENGTH_LIMIT_ORDER_OK=1" in lines
    assert "DLP_UNSAFE_REPLACEMENT_OUTPUT_ZERO=1" in lines
    assert "DLP_OBSERVED_CONFUSABLE_ASSET_OK=1" in lines
    assert result.stderr == ""
