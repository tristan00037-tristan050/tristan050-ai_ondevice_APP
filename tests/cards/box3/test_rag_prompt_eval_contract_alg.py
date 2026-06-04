"""ALG rag_prompt eval 정합 (PR #781, 2026-06-04) — verdict-only 40 case eval set
의 무결성을 잠근다 (digest/regression_tag 만, raw 0).
"""
from __future__ import annotations

from pathlib import Path

from butler_pc_core.cards.box3.eval.evaluate_rag_prompt_contract import evaluate_cases


def test_eval_cases_verdict_only_and_40_samples():
    path = Path(__file__).resolve().parents[3] / "butler_pc_core" / "cards" / "box3" / "eval" / "box3_rag_prompt_cases_v1_2.jsonl"
    report = evaluate_cases(path)
    assert report["pass"] is True
    assert report["sample_count"] == 40
    assert report["table_or_figure_count"] >= 8
    assert report["raw_key_hit_count"] == 0
    required_tags = {
        "positive_grounded",
        "abstain_slot",
        "injection_defense",
        "no_name_hallucination",
        "pr780_blocked_regression",
    }
    assert required_tags.issubset(set(report["regression_tags_present"]))
