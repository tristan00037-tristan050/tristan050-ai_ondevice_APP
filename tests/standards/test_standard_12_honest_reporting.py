"""Standard 12 — Honest Reporting Pattern sentinel (5건)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ci.check_standard_12 import (  # noqa: E402
    ALLOWED_STATUS, requires_root_cause_reeval,
    scan_forbidden, validate_honest_report, validate_status_line,
)


def _ok_report() -> dict:
    return {
        "expected_vs_observed": {"expected": 0.86, "observed": 0.8702},
        "delta": 0.0264,
        "natural_shortage": False,
    }


# ── #1 expected_vs_observed 명시 의무 ────────────────────────────────────
def test_expected_vs_observed_required():
    assert validate_honest_report(_ok_report()) == []
    # expected_vs_observed 누락 → 위반
    bad = _ok_report()
    del bad["expected_vs_observed"]
    assert any("expected_vs_observed" in i for i in validate_honest_report(bad))
    # observed 누락 → 위반
    bad2 = _ok_report()
    bad2["expected_vs_observed"] = {"expected": 0.86}
    assert any("observed" in i for i in validate_honest_report(bad2))


# ── #2 delta=0 도 명시 의무 ──────────────────────────────────────────────
def test_delta_zero_must_be_reported():
    # delta 키 자체가 없으면 위반 (0 이어도 명시해야 함)
    bad = _ok_report()
    del bad["delta"]
    assert any("delta" in i for i in validate_honest_report(bad))
    # delta=0.0 명시는 정합 (값이 0 이라고 생략 불가)
    zero = _ok_report()
    zero["delta"] = 0.0
    assert validate_honest_report(zero) == []


# ── #3 natural shortage 명시 의무 ────────────────────────────────────────
def test_natural_shortage_must_be_specified():
    # natural_shortage=true 인데 note 미명시 → 위반
    bad = _ok_report()
    bad["natural_shortage"] = True
    assert any("natural_shortage" in i for i in validate_honest_report(bad))
    # note 명시 → 정합
    good = _ok_report()
    good["natural_shortage"] = True
    good["natural_shortage_note"] = "control_clean pool 소진 후 multi-category fallback"
    assert validate_honest_report(good) == []


# ── #4 MEASURED_ONLY/PATCH PR 에서 PROCEED 금지 ──────────────────────────
def test_no_proceed_verdict_in_measured_only_pr():
    assert "PROCEED" not in ALLOWED_STATUS
    # 정상 본문
    ok_body = "STATUS=MEASURED_ONLY\n\n정착 PR 본문."
    assert validate_status_line(ok_body) == []
    # PROCEED 토큰 출현 → 위반
    bad_body = "STATUS=PATCH_CONTINUE\n\n결과: PROCEED 로 전환 가능."
    issues = validate_status_line(bad_body)
    assert any("PROCEED" in i for i in issues)
    # 허용되지 않은 STATUS → 위반
    assert validate_status_line("STATUS=PROCEED\n") != []
    # forbidden 패턴 스캔
    assert "PROCEED" in "|".join(scan_forbidden("결론: PROCEED"))


# ── #5 latent bug 패턴 정합 — 추정 vs 실측 괴리 시 재평가 의무 (PR #725) ──
def test_latent_bug_pattern_정합():
    # 추정 60, 실측 5 → 재평가 의무 (관측이 추정의 50% 미만)
    assert requires_root_cause_reeval(expected=60, observed=5) is True
    # 추정 60, 실측 55 → 재평가 불요 (정상 범위)
    assert requires_root_cause_reeval(expected=60, observed=55) is False
    # 추정 0 (추정 자체 없음) → 재평가 불요
    assert requires_root_cause_reeval(expected=0, observed=0) is False
    # 측정값 임의 조정 신호는 forbidden 패턴으로 탐지
    assert scan_forbidden("측정값을 임의 조정하여 통과시켰다")
