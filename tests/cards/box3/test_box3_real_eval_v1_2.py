"""융합 eval — 골격 #770 verdict-only 평가기(alg fixed_eval 40건) 재사용.

verdict-only/digest-safe proxy 이며 실제 재작성 측정·실제 학습은 0이다.
"""
from __future__ import annotations

from pathlib import Path

import butler_pc_core.cards.box3 as box3_pkg
from butler_pc_core.cards.box3.eval.evaluate_box3_verdict_only import evaluate_cases, load_eval_cases

_EVAL_PATH = Path(box3_pkg.__file__).parent / "eval" / "fixed_eval_cases.jsonl"


def test_fixed_eval_set_has_forty_cases_with_table_figure_coverage():
    cases = load_eval_cases(_EVAL_PATH)
    result = evaluate_cases(cases)
    summary = result["summary"]
    assert summary["sample_count"] == 40
    assert summary["table_figure_case_count"] >= 8
    assert summary["pass_thresholds_met_by_proxy"] is True


def test_fixed_eval_is_verdict_only_and_leak_zero():
    cases = load_eval_cases(_EVAL_PATH)
    summary = evaluate_cases(cases)["summary"]
    assert summary["metric_is_real_rewrite_measurement"] is False
    assert summary["raw_leak_zero"] is True
    assert summary["external_send_zero"] is True
