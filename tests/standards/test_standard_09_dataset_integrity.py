"""Standard 9 — Dataset Integrity Fail-Closed sentinel (7건)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ci.check_standard_09 import (  # noqa: E402
    COVERAGE_REPORT_FIELDS, FAIL_CLASSES,
    audit_evidence, classify_coverage, find_evaluation_evidence_dirs,
    validate_coverage_report,
)


def _ok_report() -> dict:
    return {
        "coverage_checked": True, "expected_samples": 500,
        "measured_samples": 500, "missing_count": 0, "missing_ids": [],
        "extra_count": 0, "extra_ids": [], "gold_duplicate_count": 0,
        "gold_duplicate_ids": [], "prediction_duplicate_count": 0,
        "prediction_duplicate_ids": [], "fail_class": None,
    }


# ── #1 coverage_report 12 필드 필수 ──────────────────────────────────────
def test_coverage_report_12_fields_required():
    assert len(COVERAGE_REPORT_FIELDS) == 12
    # 정합 report 는 위반 0건
    assert validate_coverage_report(_ok_report()) == []
    # 필드 1개 누락 → fail-closed
    broken = _ok_report()
    del broken["gold_duplicate_ids"]
    issues = validate_coverage_report(broken)
    assert any("gold_duplicate_ids" in i for i in issues)


# ── #2 gold 중복 fail-closed ─────────────────────────────────────────────
def test_gold_duplicate_fail_closed():
    fc = classify_coverage(["S1", "S2", "S2"], ["S1", "S2"])
    assert fc == "GOLD_SAMPLE_ID_DUPLICATE"
    assert fc in FAIL_CLASSES
    # report 정합: gold dup count > 0 인데 fail_class 미설정 → 위반
    rep = _ok_report()
    rep["gold_duplicate_count"] = 1
    rep["gold_duplicate_ids"] = ["S2"]
    assert validate_coverage_report(rep), "gold dup 미반영 fail_class 미탐지"


# ── #3 prediction 중복 fail-closed ───────────────────────────────────────
def test_prediction_duplicate_fail_closed():
    fc = classify_coverage(["S1", "S2"], ["S1", "S2", "S2"])
    assert fc == "FULL_EVAL_COVERAGE_MISMATCH"
    # missing 도 동일 fail_class
    assert classify_coverage(["S1", "S2", "S3"], ["S1", "S2"]) == \
        "FULL_EVAL_COVERAGE_MISMATCH"
    # gold 중복이 prediction 중복보다 우선
    assert classify_coverage(["S1", "S1"], ["S1", "S2", "S2"]) == \
        "GOLD_SAMPLE_ID_DUPLICATE"


# ── #4 baseline / patched mode 분리 산식 필수 ────────────────────────────
def test_mode_separation_required():
    from scripts.eval.pr727_branch_d2_targeted_deadline import measure_deadline
    items = [{"sample_id": "T1", "text": "마감이 언제까지인가요",
              "deadline_type": "NONE"}]
    preds = [{"sample_id": "T1",
              "pred": {"deadline_type": "HARD", "deadline_is_actionable": True}}]
    base = measure_deadline(items, preds, "baseline_d1")
    patched = measure_deadline(items, preds, "d2_targeted")
    # mode 가 산출물에 명시되어야 함
    assert base["mode"] == "baseline_d1"
    assert patched["mode"] == "d2_targeted"
    assert base["computed_from_d2_actionable"] is False
    assert patched["computed_from_d2_actionable"] is True
    # 미지정 mode 는 fail-closed
    try:
        measure_deadline(items, preds, "unknown_mode")
        raise AssertionError("unknown mode 가 fail-closed 되지 않음")
    except ValueError:
        pass


# ── #5 D-2 mode actionable 산식 정합 (PR #727) ───────────────────────────
def test_d2_actionable_산식_정합():
    from scripts.eval.pr727_branch_d2_targeted_deadline import d2_classify
    # D2-C INQUIRY → non-actionable
    assert d2_classify("마감이 언제까지인가요", "HARD")[1] is False
    # D2-A HARD → actionable
    assert d2_classify("내일까지 제출", "SOFT")[1] is True
    # 미매칭 + orig_actionable 명시 → 모델 원본 보존
    assert d2_classify("회의록 정리", "NONE", True)[1] is True
    assert d2_classify("회의록 정리", "NONE", False)[1] is False
    # 미매칭 + orig_actionable 미지정 → pd_orig 파생 (2-arg 하위호환)
    assert d2_classify("회의록 정리", "HARD")[1] is True
    assert d2_classify("회의록 정리", "NONE")[1] is False


# ── #6 coverage_report 0건 fail-closed (Codex P1-C) ──────────────────────
def test_coverage_report_missing_fail_closed(tmp_path):
    """평가 evidence 존재 + coverage_report.json 0건 → ok=false."""
    # 평가 evidence (branch_* + summary.md) 존재, coverage_report 없음
    d = tmp_path / "evidence" / "day99" / "branch_test"
    d.mkdir(parents=True)
    (d / "summary.md").write_text("평가 evidence", encoding="utf-8")
    (d / "full_eval_500_x.json").write_text("{}", encoding="utf-8")

    assert find_evaluation_evidence_dirs(tmp_path), "평가 evidence 미검출"
    result = audit_evidence(tmp_path)
    assert result["ok"] is False, "coverage_report 0건인데 fail-open"
    classes = {v.get("fail_class") for v in result["violations"]}
    assert "COVERAGE_REPORT_MISSING" in classes
    assert result["eval_evidence_dirs_count"] >= 1

    # coverage_report 추가 → fail-closed 해소
    cov = {
        "coverage_checked": True, "expected_samples": 500,
        "measured_samples": 500, "missing_count": 0, "missing_ids": [],
        "extra_count": 0, "extra_ids": [], "gold_duplicate_count": 0,
        "gold_duplicate_ids": [], "prediction_duplicate_count": 0,
        "prediction_duplicate_ids": [], "fail_class": None,
    }
    (d / "coverage_report.json").write_text(
        json.dumps(cov, ensure_ascii=False), encoding="utf-8")
    assert audit_evidence(tmp_path)["ok"] is True

    # 평가 evidence 자체가 없으면 위반 아님 (codification PR 등)
    empty = audit_evidence(tmp_path / "nonexistent")
    assert empty["ok"] is True


# ── #7 audit_evidence() return path 정합 — P1-C 명확 검증 ────────────────
def test_coverage_report_missing_fail_closed_actual_path(tmp_path):
    """실제 audit_evidence() return path 가 fail-closed 정합 작동 검증.

    Codex P1-C — `ok` 가 violations 뿐 아니라 missing_required_artifact 도
    반영하는지, return dict 가 두 fail-closed 신호를 모두 노출하는지 검증.
    """
    # case 1: 평가 evidence 존재 + coverage_report 0건 → fail-closed
    eval_dir = tmp_path / "evidence" / "day99" / "branch_test"
    eval_dir.mkdir(parents=True)
    (eval_dir / "summary.md").write_text("test summary", encoding="utf-8")

    result = audit_evidence(tmp_path)
    assert result["ok"] is False, "fail-closed 차단 필요"
    assert result["missing_required_artifact"] is True
    assert any(v.get("fail_class") == "COVERAGE_REPORT_MISSING"
               for v in result["violations"])
    assert result["eval_evidence_dirs_count"] == 1
    assert result["checked"] == 0

    # case 2: coverage_report 추가 (정합) → ok=true (해소)
    cov = {
        "coverage_checked": True, "expected_samples": 500,
        "measured_samples": 500, "missing_count": 0, "missing_ids": [],
        "extra_count": 0, "extra_ids": [], "gold_duplicate_count": 0,
        "gold_duplicate_ids": [], "prediction_duplicate_count": 0,
        "prediction_duplicate_ids": [], "fail_class": None,
    }
    (eval_dir / "coverage_report.json").write_text(
        json.dumps(cov, ensure_ascii=False), encoding="utf-8")
    resolved = audit_evidence(tmp_path)
    assert resolved["ok"] is True
    assert resolved["missing_required_artifact"] is False
    assert resolved["checked"] == 1

    # case 3: 평가 evidence 부재 → ok=true (codification PR 정합)
    bare = tmp_path / "bare"
    (bare / "evidence" / "day22" / "standards_codification").mkdir(parents=True)
    none_eval = audit_evidence(bare)
    assert none_eval["ok"] is True
    assert none_eval["missing_required_artifact"] is False
    assert none_eval["eval_evidence_dirs_count"] == 0
