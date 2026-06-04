from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from .constants import (
    BLOCK,
    PASS_FUSION_EVAL,
    PARTIAL,
    FAIL_BLOCK_GENERAL_PC_BUDGET_EXCEEDED,
    FAIL_PARTIAL_FUSION_NO_GAIN,
    GENERAL_PC_LIMITS,
    SCHEMA_VERSION_METRIC_COMPARISON,
)
from .security import assert_no_raw_or_path_material, stable_json_digest


@dataclass(frozen=True)
class Box3MetricSnapshot:
    label: str
    unsupported_count: int
    citation_accuracy: float
    supported_count: int
    format_compliance: float
    style_compliance: float
    latency_ms: int
    peak_rss_mb: int
    regression_new_failures: int
    sample_digest: str

    def __post_init__(self) -> None:
        if self.unsupported_count < 0 or self.supported_count < 0 or self.regression_new_failures < 0:
            raise ValueError("METRIC_COUNT_INVALID")
        for value in [self.citation_accuracy, self.format_compliance, self.style_compliance]:
            if not (0.0 <= float(value) <= 1.0):
                raise ValueError("METRIC_RATE_INVALID")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        assert_no_raw_or_path_material(payload)
        return payload


@dataclass(frozen=True)
class MetricComparison:
    schema_version: str
    before: Box3MetricSnapshot
    after: Box3MetricSnapshot
    unsupported_delta: int
    status: Literal["PASS_FUSION_EVAL", "FUSION_EVAL_NO_GAIN", "PARTIAL", "BLOCKED"]
    fail_class: str | None
    comparison_digest: str | None = None
    raw_saved_zero: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["comparison_digest"] is None:
            core = {k: v for k, v in payload.items() if k != "comparison_digest"}
            payload["comparison_digest"] = stable_json_digest(core)
        assert_no_raw_or_path_material(payload)
        return payload


def compare_box3_metrics(before: Box3MetricSnapshot, after: Box3MetricSnapshot) -> MetricComparison:
    unsupported_delta = before.unsupported_count - after.unsupported_count
    if after.regression_new_failures > 0:
        return _cmp(before, after, unsupported_delta, "BLOCKED", "BLOCK_REGRESSION_NEW_FAILURE")
    if after.peak_rss_mb > GENERAL_PC_LIMITS["max_peak_rss_mb"] or after.latency_ms > GENERAL_PC_LIMITS["max_latency_ms"]:
        return _cmp(before, after, unsupported_delta, "BLOCKED", FAIL_BLOCK_GENERAL_PC_BUDGET_EXCEEDED)
    if (
        after.unsupported_count == 0
        and after.citation_accuracy >= 0.95
        and after.supported_count >= 1
        and after.format_compliance >= 0.85
        and after.style_compliance >= 0.70
    ):
        if unsupported_delta <= 0 and before.unsupported_count == 0:
            return _cmp(before, after, unsupported_delta, "FUSION_EVAL_NO_GAIN", FAIL_PARTIAL_FUSION_NO_GAIN)
        return _cmp(before, after, unsupported_delta, PASS_FUSION_EVAL, None)
    return _cmp(before, after, unsupported_delta, PARTIAL, "PARTIAL_FUSION_METRIC_GATE_NOT_MET")


def _cmp(before, after, delta, status, fail_class):
    return MetricComparison(SCHEMA_VERSION_METRIC_COMPARISON, before, after, delta, status, fail_class)
