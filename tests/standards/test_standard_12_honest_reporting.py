"""Standard 12 — Honest Reporting Pattern sentinel (7건)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ci.check_standard_12 import (  # noqa: E402
    ALLOWED_STATUS, audit_summaries, is_proceed_violation_in_text,
    requires_root_cause_reeval, scan_forbidden,
    validate_honest_report, validate_status_line,
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


# ── #6 PROCEED 필터 runtime crash 차단 (Codex P1-A) ──────────────────────
def test_proceed_filter_no_runtime_crash():
    """variable-width lookbehind 제거 — line/context 기반 판정."""
    # crash 없이 실행
    explain = "PROCEED 절대 금지 — 정착 PR 본문에 출현 불가."
    assert is_proceed_violation_in_text(explain) is False
    # 같은 line 부정 단어 → 설명문
    assert is_proceed_violation_in_text("금지 verdict (PROCEED) 미사용") is False
    # 부정 단어 없는 PROCEED → 위반
    assert is_proceed_violation_in_text("결론: PROCEED 로 전환") is True
    assert is_proceed_violation_in_text("verdict: PROCEED") is True
    # 다중 line 혼재 — 위반 line 1개라도 있으면 violation
    mixed = "PROCEED 절대 금지\n결론: PROCEED"
    assert is_proceed_violation_in_text(mixed) is True
    # PROCEED 부재 → False
    assert is_proceed_violation_in_text("STATUS=MEASURED_ONLY") is False


# ── #7 evidence scan 범위 — day22 hardcoded 회귀 차단 (Codex P1-B) ───────
def test_evidence_scan_covers_all_day_folders(tmp_path):
    """audit_summaries 가 day22 외 day23+ 폴더도 검출."""
    for day in ["day22", "day23", "day99"]:
        d = tmp_path / "evidence" / day / "branch_test"
        d.mkdir(parents=True)
        (d / "summary.md").write_text("결론: PROCEED 로 전환", encoding="utf-8")
    result = audit_summaries(tmp_path)
    assert result["checked"] == 3
    flagged = {v["file"] for v in result["violations"]}
    # day23 / day99 가 모두 검출되어야 함 (hardcoded day22 회귀 차단)
    assert any("day23" in f for f in flagged)
    assert any("day99" in f for f in flagged)
    assert result["ok"] is False
    # 정상 summary 만 있으면 ok
    (tmp_path / "evidence/day23/branch_test/summary.md").write_text(
        "STATUS=MEASURED_ONLY\n정상 보고.", encoding="utf-8")
    (tmp_path / "evidence/day22/branch_test/summary.md").write_text(
        "STATUS=MEASURED_ONLY", encoding="utf-8")
    (tmp_path / "evidence/day99/branch_test/summary.md").write_text(
        "STATUS=MEASURED_ONLY", encoding="utf-8")
    assert audit_summaries(tmp_path)["ok"] is True
