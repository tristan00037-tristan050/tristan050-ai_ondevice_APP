from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from .contracts import is_sha256, stable_digest


BUILD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class BenchmarkSample:
    schema_version: str
    box_id: Literal["1", "3"]
    complexity_bucket: str
    fixture_id: str
    input_digest: str
    device_id_digest: str
    build_sha: str
    model_digest: str
    variant_id: str
    run_kind: Literal["cold", "warm"]
    iteration: int
    load_ms: float
    ttft_ms: float
    total_latency_ms: float
    tokens_in: int
    tokens_out: int
    tokens_per_second: float
    rss_before_bytes: int
    rss_peak_bytes: int
    rss_after_bytes: int
    available_memory_before_bytes: int
    available_memory_after_bytes: int
    thermal_before: str
    thermal_after: str
    low_power_mode: bool | None
    battery_delta_percent: float | None
    quality_gate_pass: bool
    schema_pass: bool
    dlp_pass: bool
    grounding_pass: bool
    escalation_recommended: bool
    device_profile_valid: bool
    failed: bool

    def validate(self) -> None:
        if self.schema_version != "butler.model_tier_benchmark_sample.v1":
            raise ValueError("BENCHMARK_SAMPLE_SCHEMA_INVALID")
        if self.box_id not in {"1", "3"}:
            raise ValueError("BENCHMARK_BOX_INVALID")
        if self.run_kind not in {"cold", "warm"}:
            raise ValueError("BENCHMARK_RUN_KIND_INVALID")
        if not self.fixture_id or len(self.fixture_id) > 128 or "/" in self.fixture_id:
            raise ValueError("BENCHMARK_FIXTURE_ID_INVALID")
        allowed_buckets = {
            "1": {"simple", "ambiguous", "multi_intent_attachment"},
            "3": {"short", "medium", "long_multi_evidence"},
        }
        if self.complexity_bucket not in allowed_buckets[self.box_id]:
            raise ValueError("BENCHMARK_COMPLEXITY_BUCKET_INVALID")
        for digest in (self.input_digest, self.device_id_digest, self.model_digest):
            if not is_sha256(digest):
                raise ValueError("BENCHMARK_DIGEST_INVALID")
        if not BUILD_SHA_RE.fullmatch(self.build_sha):
            raise ValueError("BENCHMARK_BUILD_SHA_INVALID")
        if isinstance(self.iteration, bool) or self.iteration < 0:
            raise ValueError("BENCHMARK_ITERATION_INVALID")
        for value in (
            self.load_ms,
            self.ttft_ms,
            self.total_latency_ms,
            self.tokens_per_second,
            self.battery_delta_percent or 0.0,
        ):
            if not math.isfinite(value) or value < 0:
                raise ValueError("BENCHMARK_METRIC_INVALID")
        for value in (
            self.tokens_in,
            self.tokens_out,
            self.rss_before_bytes,
            self.rss_peak_bytes,
            self.rss_after_bytes,
            self.available_memory_before_bytes,
            self.available_memory_after_bytes,
        ):
            if isinstance(value, bool) or value < 0:
                raise ValueError("BENCHMARK_MEMORY_INVALID")
        if self.rss_peak_bytes < max(self.rss_before_bytes, self.rss_after_bytes):
            raise ValueError("BENCHMARK_RSS_PEAK_INVALID")
        thermal_values = {"NOMINAL", "FAIR", "SERIOUS", "CRITICAL", "UNKNOWN"}
        if self.thermal_before not in thermal_values or self.thermal_after not in thermal_values:
            raise ValueError("BENCHMARK_THERMAL_STATE_INVALID")
        if self.low_power_mode is not None and not isinstance(self.low_power_mode, bool):
            raise ValueError("BENCHMARK_LOW_POWER_MODE_INVALID")
        for value in (
            self.quality_gate_pass,
            self.schema_pass,
            self.dlp_pass,
            self.grounding_pass,
            self.escalation_recommended,
            self.device_profile_valid,
            self.failed,
        ):
            if not isinstance(value, bool):
                raise ValueError("BENCHMARK_BOOLEAN_INVALID")


def percentile(values: Iterable[float], quantile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_benchmark(samples: Iterable[BenchmarkSample]) -> dict[str, Any]:
    rows = list(samples)
    if not rows:
        raise ValueError("BENCHMARK_SAMPLES_REQUIRED")
    for row in rows:
        row.validate()
    identity = {
        (row.device_id_digest, row.variant_id, row.model_digest, row.build_sha, row.box_id)
        for row in rows
    }
    if len(identity) != 1:
        raise ValueError("BENCHMARK_IDENTITY_MIXED")
    fixture_buckets = {
        fixture_id: {row.complexity_bucket for row in rows if row.fixture_id == fixture_id}
        for fixture_id in {row.fixture_id for row in rows}
    }
    if any(len(buckets) != 1 for buckets in fixture_buckets.values()):
        raise ValueError("BENCHMARK_FIXTURE_BUCKET_DRIFT")
    cold_count = sum(row.run_kind == "cold" for row in rows)
    warm_count = sum(row.run_kind == "warm" for row in rows)
    fixture_ids = set(fixture_buckets)
    warm_by_fixture = {
        fixture_id: sum(
            row.run_kind == "warm" and row.fixture_id == fixture_id for row in rows
        )
        for fixture_id in fixture_ids
    }
    complexity_counts = {
        bucket: len({row.fixture_id for row in rows if row.complexity_bucket == bucket})
        for bucket in sorted({row.complexity_bucket for row in rows})
    }
    count = len(rows)

    def rate(predicate) -> float:
        return round(sum(1 for row in rows if predicate(row)) / count, 6)

    result = {
        "schema_version": "butler.model_tier_benchmark_result.v1",
        "box_id": rows[0].box_id,
        "device_id_digest": rows[0].device_id_digest,
        "variant_id": rows[0].variant_id,
        "model_digest": rows[0].model_digest,
        "build_sha": rows[0].build_sha,
        "sample_count": count,
        "fixture_count": len(fixture_ids),
        "complexity_counts": complexity_counts,
        "cold_count": cold_count,
        "warm_count": warm_count,
        "protocol_complete": bool(
            cold_count >= 3
            and len(fixture_ids) >= 30
            and len(complexity_counts) == 3
            and all(value >= 10 for value in complexity_counts.values())
            and all(value >= 10 for value in warm_by_fixture.values())
        ),
        "raw_text_logged": False,
        "external_send_zero": True,
        "metrics": {
            "load_ms_p50": round(percentile((row.load_ms for row in rows), 0.50), 3),
            "load_ms_p95": round(percentile((row.load_ms for row in rows), 0.95), 3),
            "ttft_ms_p50": round(percentile((row.ttft_ms for row in rows), 0.50), 3),
            "ttft_ms_p95": round(percentile((row.ttft_ms for row in rows), 0.95), 3),
            "total_latency_ms_p50": round(
                percentile((row.total_latency_ms for row in rows), 0.50), 3
            ),
            "total_latency_ms_p95": round(
                percentile((row.total_latency_ms for row in rows), 0.95), 3
            ),
            "tokens_per_second_p50": round(
                percentile((row.tokens_per_second for row in rows), 0.50), 3
            ),
            "tokens_per_second_p95": round(
                percentile((row.tokens_per_second for row in rows), 0.95), 3
            ),
            "tokens_in_p50": round(percentile((float(row.tokens_in) for row in rows), 0.50), 3),
            "tokens_out_p50": round(percentile((float(row.tokens_out) for row in rows), 0.50), 3),
            "rss_peak_bytes_p50": round(
                percentile((float(row.rss_peak_bytes) for row in rows), 0.50), 3
            ),
            "rss_peak_bytes_p95": round(
                percentile((float(row.rss_peak_bytes) for row in rows), 0.95), 3
            ),
            "failure_rate": rate(lambda row: row.failed),
            "quality_pass_rate": rate(lambda row: row.quality_gate_pass),
            "schema_pass_rate": rate(lambda row: row.schema_pass),
            "dlp_pass_rate": rate(lambda row: row.dlp_pass),
            "grounding_pass_rate": rate(lambda row: row.grounding_pass),
            "escalation_recommendation_rate": rate(
                lambda row: row.escalation_recommended
            ),
            "device_profile_invalid_rate": rate(
                lambda row: not row.device_profile_valid
            ),
            "available_memory_drop_bytes_p95": round(
                percentile(
                    (
                        float(
                            max(
                                0,
                                row.available_memory_before_bytes
                                - row.available_memory_after_bytes,
                            )
                        )
                        for row in rows
                    ),
                    0.95,
                ),
                3,
            ),
        },
    }
    result["result_digest"] = stable_digest(result)
    return result
