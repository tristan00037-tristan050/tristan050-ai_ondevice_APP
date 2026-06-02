from __future__ import annotations

from typing import Any

from .claim_grounding import ClaimGroundingSummary
from .types import Box3Format, Box3Style


REAL_METRIC_THRESHOLDS = {
    "fixed_eval_sample_count": 40,
    "unsupported_claim_rate": 0.0,
    "no_evidence_rate": 0.05,
    "citation_accuracy": 0.95,
    "format_match_score": 0.85,
    "style_match_score": 0.70,
    "table_figure_grounding_score": 0.70,
}


def build_real_metrics(
    *,
    claim_summary: ClaimGroundingSummary,
    format_result: Box3Format,
    style_result: Box3Style,
    fixed_eval_sample_count: int,
    table_figure_grounding_score: float,
) -> dict[str, Any]:
    metrics = {
        "schema_version": "box3.real_metrics.v1_2",
        "metric_basis": "claim_level_grounding_real_verification",
        "fixed_eval_sample_count": fixed_eval_sample_count,
        "factual_claim_count": claim_summary.factual_claim_count,
        "unsupported_claim_rate": claim_summary.unsupported_claim_rate,
        "no_evidence_rate": claim_summary.no_evidence_rate,
        "citation_accuracy": claim_summary.citation_accuracy,
        "format_match_score": format_result["format_match_score"],
        "style_match_score": style_result["style_match_score"],
        "table_figure_grounding_score": round(float(table_figure_grounding_score), 4),
        "thresholds": dict(REAL_METRIC_THRESHOLDS),
    }
    metrics["pass"] = real_metrics_pass(metrics)
    return metrics


def real_metrics_pass(metrics: dict[str, Any]) -> bool:
    return bool(
        metrics["fixed_eval_sample_count"] >= REAL_METRIC_THRESHOLDS["fixed_eval_sample_count"]
        and metrics["unsupported_claim_rate"] <= REAL_METRIC_THRESHOLDS["unsupported_claim_rate"]
        and metrics["no_evidence_rate"] <= REAL_METRIC_THRESHOLDS["no_evidence_rate"]
        and metrics["citation_accuracy"] >= REAL_METRIC_THRESHOLDS["citation_accuracy"]
        and metrics["format_match_score"] >= REAL_METRIC_THRESHOLDS["format_match_score"]
        and metrics["style_match_score"] >= REAL_METRIC_THRESHOLDS["style_match_score"]
        and metrics["table_figure_grounding_score"] >= REAL_METRIC_THRESHOLDS["table_figure_grounding_score"]
    )


def metric_fail_class(metrics: dict[str, Any]) -> str | None:
    if metrics["fixed_eval_sample_count"] < REAL_METRIC_THRESHOLDS["fixed_eval_sample_count"]:
        return "FIXED_EVAL_SAMPLE_COUNT_BELOW_GATE"
    if metrics["unsupported_claim_rate"] > REAL_METRIC_THRESHOLDS["unsupported_claim_rate"]:
        return "BLOCK_UNSUPPORTED_CLAIM"
    if metrics["no_evidence_rate"] > REAL_METRIC_THRESHOLDS["no_evidence_rate"]:
        return "NEEDS_REVIEW_NO_EVIDENCE_RATE_ABOVE_GATE"
    if metrics["citation_accuracy"] < REAL_METRIC_THRESHOLDS["citation_accuracy"]:
        return "CITATION_ACCURACY_BELOW_GATE"
    if metrics["format_match_score"] < REAL_METRIC_THRESHOLDS["format_match_score"]:
        return "FORMAT_MATCH_BELOW_GATE"
    if metrics["style_match_score"] < REAL_METRIC_THRESHOLDS["style_match_score"]:
        return "STYLE_MATCH_BELOW_GATE"
    if metrics["table_figure_grounding_score"] < REAL_METRIC_THRESHOLDS["table_figure_grounding_score"]:
        return "TABLE_FIGURE_GROUNDING_BELOW_GATE"
    return None
