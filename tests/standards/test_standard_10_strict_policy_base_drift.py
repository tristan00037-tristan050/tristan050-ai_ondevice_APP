"""Standard 10 — Strict Policy Base Drift sentinel (8건)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ci.check_standard_10 import (  # noqa: E402
    DRIFT_HOLD, DRIFT_PATCH_CONTINUE, METRIC_THRESHOLDS,
    audit_evidence, classify_drift, detect_metric_threshold_changes,
    is_version_bumped, parse_semver, validate_before_after,
    validate_drift_report,
)


# ── #1 metric threshold 변경 검출 ────────────────────────────────────────
def test_metric_threshold_change_detected():
    # 정착 기준 그대로 → 변경 0건
    assert detect_metric_threshold_changes(dict(METRIC_THRESHOLDS)) == []
    # deadline_f1 기준을 낮추면 검출
    tampered = dict(METRIC_THRESHOLDS)
    tampered["deadline_f1"] = 0.80
    changed = detect_metric_threshold_changes(tampered)
    assert "deadline_f1" in changed
    # auto_apply_precision 하향도 검출
    tampered2 = {"auto_apply_precision": 0.90}
    assert "auto_apply_precision" in detect_metric_threshold_changes(tampered2)


# ── #2 label guide version bump 의무 (SemVer) ────────────────────────────
def test_label_guide_version_bump_required():
    assert parse_semver("1.2.3") == (1, 2, 3)
    # 증가 → bump 정합
    assert is_version_bumped("1.0.0", "1.0.1") is True
    assert is_version_bumped("1.0.0", "1.1.0") is True
    assert is_version_bumped("1.9.9", "2.0.0") is True
    # 동일/감소 → bump 아님
    assert is_version_bumped("1.0.0", "1.0.0") is False
    assert is_version_bumped("2.0.0", "1.9.9") is False
    # SemVer 형식 위반 → ValueError
    for bad in ["1.0", "v1.0.0", "1.0.x", "1.0.0.0"]:
        try:
            parse_semver(bad)
            raise AssertionError(f"SemVer 위반 미검출: {bad}")
        except ValueError:
            pass


# ── #3 before/after comparison 필수 ──────────────────────────────────────
def test_before_after_comparison_required():
    ok = {"comparison": [
        {"metric": "deadline_f1", "before": 0.8438, "after": 0.8702,
         "delta": 0.0264}]}
    assert validate_before_after(ok) == []
    # comparison 누락 → 위반
    assert validate_before_after({}) != []
    # 필드 누락 → 위반
    miss = {"comparison": [{"metric": "deadline_f1", "before": 0.84}]}
    assert any("after" in i for i in validate_before_after(miss))
    # delta 불일치 → 위반
    bad = {"comparison": [
        {"metric": "x", "before": 0.5, "after": 0.7, "delta": 0.1}]}
    assert any("delta" in i for i in validate_before_after(bad))


# ── #4 policy drift 5% threshold ─────────────────────────────────────────
def test_policy_drift_threshold_5_percent():
    # drift < 5% → OK
    assert classify_drift(0.86, 0.87) == "OK"
    # 5% ≤ drift < 20% → PATCH_CONTINUE
    assert classify_drift(0.80, 0.86) == "PATCH_CONTINUE"   # 7.5%
    assert classify_drift(1.00, 1.05) == "PATCH_CONTINUE"   # 5%
    # drift ≥ 20% → HOLD
    assert classify_drift(0.50, 0.70) == "HOLD"             # 40%
    # 경계 상수 정합
    assert DRIFT_PATCH_CONTINUE == 0.05
    assert DRIFT_HOLD == 0.20
    # old=0 → new 절대값 기준
    assert classify_drift(0.0, 0.30) == "HOLD"


# ── #5 drift report 형식 정합 ────────────────────────────────────────────
def test_drift_report_format_정합():
    ok = {
        "policy_name": "deadline strength taxonomy",
        "old_policy_version": "1.0.0", "new_policy_version": "1.1.0",
        "drift_rate": 0.07, "drift_class": "PATCH_CONTINUE",
        "samples_compared": 500,
    }
    assert validate_drift_report(ok) == []
    # 필드 누락 → 위반
    assert any("samples_compared" in i
               for i in validate_drift_report({k: v for k, v in ok.items()
                                               if k != "samples_compared"}))
    # version bump 누락 → 위반
    no_bump = dict(ok); no_bump["new_policy_version"] = "1.0.0"
    assert any("version bump" in i for i in validate_drift_report(no_bump))
    # drift_class 불일치 → 위반
    mismatch = dict(ok); mismatch["drift_class"] = "OK"
    assert any("drift_class" in i for i in validate_drift_report(mismatch))


# ── #6 audit_evidence fail-closed — artifact 누락 (Codex P1-A) ───────────
def test_audit_evidence_fail_closed_when_artifacts_missing(tmp_path):
    """Standard 10 적용 평가 evidence 존재 + before_after 0건 → ok=false."""
    d = tmp_path / "evidence" / "day99" / "branch_test"
    d.mkdir(parents=True)
    (d / "summary.md").write_text("eval evidence", encoding="utf-8")
    result = audit_evidence(tmp_path)
    assert result["ok"] is False, "fail-open — artifact 누락이 통과"
    assert result["missing_required_artifact"] is True
    assert any(v.get("fail_class") == "STANDARD_10_BEFORE_AFTER_MISSING"
               for v in result["violations"])
    assert result["eval_evidence_dirs_count"] >= 1
    # before_after_comparison 추가 → 해소
    (d / "before_after_comparison.json").write_text(
        '{"comparison": [{"metric": "deadline_f1", "before": 0.84, '
        '"after": 0.87, "delta": 0.03}]}', encoding="utf-8")
    assert audit_evidence(tmp_path)["ok"] is True


# ── #7 audit_evidence — codification PR / 정착 이전 evidence 통과 (P1-A) ──
def test_audit_evidence_passes_for_codification_pr(tmp_path):
    """정착 PR (branch_* 평가 evidence 부재) + 정착 이전 evidence 는 통과."""
    # case 1: 정착 PR — branch_* 평가 evidence 부재
    cod = tmp_path / "evidence" / "day23" / "standard_x_codification"
    cod.mkdir(parents=True)
    (cod / "summary.md").write_text("codification", encoding="utf-8")
    result = audit_evidence(tmp_path)
    assert result["ok"] is True
    assert result["missing_required_artifact"] is False
    assert result["eval_evidence_dirs_count"] == 0
    # case 2: Standard 10 정착 이전(day<24) branch evidence 는 소급 요구 대상 아님
    old = tmp_path / "evidence" / "day20" / "branch_old"
    old.mkdir(parents=True)
    (old / "summary.md").write_text("pre-standard-10 eval", encoding="utf-8")
    result2 = audit_evidence(tmp_path)
    assert result2["ok"] is True, "day20 evidence 가 소급 fail-closed 됨"
    assert result2["eval_evidence_dirs_count"] == 0


# ── #8 validate_drift_report — negative drift_rate 차단 (Codex P1-B) ─────
def test_validate_drift_report_rejects_negative_rate():
    """drift_rate 음수 → NEGATIVE_DRIFT_RATE 위반 (drift 은폐 차단)."""
    neg = {
        "policy_name": "deadline strength taxonomy",
        "old_policy_version": "1.0.0", "new_policy_version": "1.1.0",
        "drift_rate": -0.3, "drift_class": "OK",
        "samples_compared": 500,
    }
    issues = validate_drift_report(neg)
    assert any("NEGATIVE_DRIFT_RATE" in i for i in issues)
    # 비음수 drift_rate 는 정상 통과
    pos = dict(neg); pos["drift_rate"] = 0.07; pos["drift_class"] = "PATCH_CONTINUE"
    assert validate_drift_report(pos) == []
    # drift_rate 누락 → 필드 누락 위반
    miss = {k: v for k, v in neg.items() if k != "drift_rate"}
    assert any("drift_rate" in i for i in validate_drift_report(miss))
