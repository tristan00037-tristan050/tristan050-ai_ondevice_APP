from __future__ import annotations

from butler_pc_core.cards.box3.lora_fusion.metric_comparison import Box3MetricSnapshot, compare_box3_metrics
from butler_pc_core.cards.box3.lora_fusion.security import sha256_text


def _snap(label: str, unsupported: int, supported: int = 2, latency: int = 2000, peak: int = 2500, failures: int = 0):
    return Box3MetricSnapshot(
        label=label,
        unsupported_count=unsupported,
        citation_accuracy=1.0,
        supported_count=supported,
        format_compliance=1.0,
        style_compliance=1.0,
        latency_ms=latency,
        peak_rss_mb=peak,
        regression_new_failures=failures,
        sample_digest=sha256_text(label),
    )


def test_pr781_regression_compare_pass_when_unsupported_removed():
    result = compare_box3_metrics(_snap("pr781", 1), _snap("fused", 0))
    assert result.status == "PASS_FUSION_EVAL"
    assert result.unsupported_delta == 1


def test_metric_no_gain_when_before_already_zero():
    result = compare_box3_metrics(_snap("before", 0), _snap("after", 0))
    assert result.status == "FUSION_EVAL_NO_GAIN"
    assert result.fail_class == "PARTIAL_FUSION_NO_GAIN"


def test_regression_failure_blocks():
    result = compare_box3_metrics(_snap("before", 1), _snap("after", 0, failures=1))
    assert result.status == "BLOCKED"
    assert result.fail_class == "BLOCK_REGRESSION_NEW_FAILURE"


def test_general_pc_budget_blocks():
    result = compare_box3_metrics(_snap("before", 1), _snap("after", 0, latency=50000))
    assert result.status == "BLOCKED"
    assert result.fail_class == "BLOCK_GENERAL_PC_BUDGET_EXCEEDED"
