from __future__ import annotations

from butler_pc_core.cards.box3.claim_grounding import ClaimGroundingSummary
from butler_pc_core.cards.box3.real_metrics import build_real_metrics, metric_fail_class, real_metrics_pass


def _summary(**overrides) -> ClaimGroundingSummary:
    base = {
        "factual_claim_count": 3,
        "supported_claim_count": 3,
        "unsupported_claim_count": 0,
        "no_evidence_claim_count": 0,
        "non_claim_count": 2,
        "unsupported_claim_rate": 0.0,
        "no_evidence_rate": 0.0,
        "citation_accuracy": 1.0,
        "claim_grounding_verified": True,
        "fail_class": None,
    }
    base.update(overrides)
    return ClaimGroundingSummary(**base)


def test_real_metrics_require_fixed_eval_40_cases_and_zero_unsupported():
    metrics = build_real_metrics(
        claim_summary=_summary(),
        format_result={"format_match_score": 1.0, "required_sections_present": True, "required_sections": []},
        style_result={"style_match_score": 1.0, "forbidden_style_zero": True},
        fixed_eval_sample_count=40,
        table_figure_grounding_score=1.0,
    )

    assert real_metrics_pass(metrics) is True
    assert metric_fail_class(metrics) is None

    metrics["unsupported_claim_rate"] = 0.0001
    assert real_metrics_pass(metrics) is False
    assert metric_fail_class(metrics) == "BLOCK_UNSUPPORTED_CLAIM"


def test_real_metrics_fail_closed_for_proxy_insufficient_counts():
    metrics = build_real_metrics(
        claim_summary=_summary(),
        format_result={"format_match_score": 1.0, "required_sections_present": True, "required_sections": []},
        style_result={"style_match_score": 1.0, "forbidden_style_zero": True},
        fixed_eval_sample_count=20,
        table_figure_grounding_score=1.0,
    )

    assert metrics["pass"] is False
    assert metric_fail_class(metrics) == "FIXED_EVAL_SAMPLE_COUNT_BELOW_GATE"
