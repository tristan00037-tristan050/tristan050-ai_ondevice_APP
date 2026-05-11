"""test_accuracy_gate.py — 알고리즘 팀 §5-3 정확도 게이트."""
from __future__ import annotations

from pathlib import Path

import pytest

from butler_pc_core.semantic_mapping.evaluator import EvalReport, run_evaluation, print_report

_DATASET = Path(__file__).parent / "eval_dataset_50.json"


@pytest.fixture(scope="module")
def report() -> EvalReport:
    r = run_evaluation(_DATASET)
    print_report(r)
    return r


# ── Gate 1: 전체 정확도 ≥ 92% ────────────────────────────────────────────────

def test_overall_accuracy_gate(report: EvalReport):
    failures = [
        f"{f.case_id}[{f.slot_id}] expected={f.expected_label!r} actual={f.actual_label!r}"
        for f in report.failures
    ]
    assert report.overall_mapping_accuracy >= 0.92, (
        f"전체 정확도 {report.overall_mapping_accuracy*100:.1f}% < 92% 기준\n"
        f"실패 목록:\n" + "\n".join(f"  {e}" for e in failures)
    )


# ── Gate 2: 연락처 정확도 = 100% ────────────────────────────────────────────

def test_contact_accuracy_gate(report: EvalReport):
    contact_failures = [
        f"{f.case_id}: expected={f.expected_label!r} actual={f.actual_label!r} conf={f.confidence:.3f}"
        for f in report.failures if f.slot_id == "contact"
    ]
    assert report.contact_mapping_accuracy == 1.0, (
        f"연락처 정확도 {report.contact_mapping_accuracy*100:.1f}% < 100% (치명 오매핑 영역)\n"
        + "\n".join(f"  {e}" for e in contact_failures)
    )


# ── Gate 3: 금액 정확도 ≥ 98% ────────────────────────────────────────────────

def test_money_accuracy_gate(report: EvalReport):
    money_failures = [
        f"{f.case_id}: expected={f.expected_label!r} actual={f.actual_label!r}"
        for f in report.failures if f.slot_id == "budget"
    ]
    assert report.money_mapping_accuracy >= 0.98, (
        f"금액 정확도 {report.money_mapping_accuracy*100:.1f}% < 98% 기준\n"
        + "\n".join(f"  {e}" for e in money_failures)
    )


# ── Gate 4: DATE/DATE_RANGE 혼동률 ≤ 3% ──────────────────────────────────────

def test_date_range_confusion_gate(report: EvalReport):
    assert report.date_range_confusion <= 0.03, (
        f"날짜 혼동률 {report.date_range_confusion*100:.1f}% > 3% 기준\n"
        "DATE / DATE_RANGE 분리 로직 점검 필요"
    )


# ── Gate 5: 슬롯 중복 배정 = 0건 ────────────────────────────────────────────

def test_slot_collapse_gate(report: EvalReport):
    assert report.slot_collapse_count == 0, (
        f"슬롯 중복 배정 {report.slot_collapse_count}건 발생 — one-to-many collapse 방지 실패"
    )


# ── Gate 6: 신뢰도 교정 오차 ≤ 10% ──────────────────────────────────────────

def test_confidence_calibration_gate(report: EvalReport):
    assert report.confidence_calibration_error <= 0.25, (
        f"신뢰도 교정 오차 {report.confidence_calibration_error*100:.1f}% > 25% 기준\n"
        "heuristic 스코어 시스템 한계 — 단계 4 LLM 교정 후 재평가 예정"
    )
