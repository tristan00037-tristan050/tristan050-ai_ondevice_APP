from __future__ import annotations

import re
from typing import Any

from .errors import ExitCode, FailClass, GateError

MEMORY_MARKS = (
    "preload_baseline", "model_loaded", "load_peak", "inference_start",
    "first_chunk", "inference_peak", "inference_end", "after_close",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_KEYS = {
    "schema_version", "sampler_binary_sha256", "sampler_config_sha256",
    "sampler_process_pid", "raw_samples_sha256", "marks", "sampler_error_count",
}
_MARK_KEYS = {
    "mark", "monotonic_ns", "target_pid_set", "rss_bytes_total", "available_memory_bytes",
    "memory_pressure", "sample_source", "sample_interval_ms", "missed_sample_count",
    "sample_count", "max_observed_gap_ms", "metal_current_allocated_size_bytes",
    "metal_recommended_max_working_set_size_bytes", "metal_unsupported_reason",
}


def validate_memory_receipt(
    receipt: dict[str, Any], *, policy: dict[str, Any], expected_pid_set: list[int],
    approved_sampler_binary_sha256: str, approved_sampler_config_sha256: str,
) -> None:
    if set(receipt) != _RECEIPT_KEYS or receipt["schema_version"] != "butler.model-tier-b.memory.v2.8":
        _block("MEMORY_RECEIPT_KEYS")
    if receipt["sampler_error_count"] != 0:
        _block("SAMPLER_ERROR")
    if receipt["sampler_binary_sha256"] != approved_sampler_binary_sha256 or receipt["sampler_config_sha256"] != approved_sampler_config_sha256:
        _block("SAMPLER_IDENTITY")
    for key in ("sampler_binary_sha256", "sampler_config_sha256", "raw_samples_sha256"):
        if not isinstance(receipt[key], str) or not _SHA256.fullmatch(receipt[key]):
            _block("SAMPLER_DIGEST")
    if type(receipt["sampler_process_pid"]) is not int or receipt["sampler_process_pid"] <= 0:
        _block("SAMPLER_PID")
    marks = receipt["marks"]
    if not isinstance(marks, list) or [item.get("mark") for item in marks] != list(MEMORY_MARKS):
        _block("MEMORY_MARK_SEQUENCE")
    if expected_pid_set != sorted(set(expected_pid_set)) or any(type(pid) is not int or pid <= 0 for pid in expected_pid_set):
        _block("EXPECTED_PID_SET")
    last_clock = 0
    for mark in marks:
        if not isinstance(mark, dict) or set(mark) != _MARK_KEYS:
            _block("MEMORY_MARK_KEYS")
        clock = mark["monotonic_ns"]
        if type(clock) is not int or clock <= last_clock:
            _block("MEMORY_CLOCK")
        last_clock = clock
        if mark["target_pid_set"] != expected_pid_set:
            _block("RSS_WRONG_PID_SCOPE")
        _positive(mark["rss_bytes_total"], "RSS")
        _positive(mark["available_memory_bytes"], "AVAILABLE_MEMORY")
        if mark["rss_bytes_total"] > policy["peak_rss_limit_bytes"]:
            _block("RSS_POLICY_LIMIT")
        if mark["available_memory_bytes"] < policy["available_memory_floor_bytes"]:
            _block("AVAILABLE_MEMORY_FLOOR")
        if mark["memory_pressure"] != "normal":
            _block("MEMORY_PRESSURE")
        if mark["sample_source"] not in {"proc_pid_rusage", "mach_task_info", "approved_sampler"}:
            _block("SAMPLE_SOURCE")
        interval = policy["sampler_interval_ms"]
        if mark["sample_interval_ms"] != interval or mark["max_observed_gap_ms"] > interval * 2:
            _block("SAMPLER_GAP_HIDDEN")
        count, missed = mark["sample_count"], mark["missed_sample_count"]
        if type(count) is not int or count <= 0 or type(missed) is not int or not 0 <= missed <= count:
            _block("SAMPLE_COUNTS")
        allowed_ppm = policy["max_missed_sample_ratio_ppm"]
        if missed * 1_000_000 > allowed_ppm * count:
            _block("MISSED_SAMPLE_RATIO")
        current = mark["metal_current_allocated_size_bytes"]
        recommended = mark["metal_recommended_max_working_set_size_bytes"]
        reason = mark["metal_unsupported_reason"]
        if current is None or recommended is None:
            if policy.get("require_metal") is True or not isinstance(reason, str) or not reason:
                _block("METAL_REQUIRED")
        elif type(current) is not int or current < 0 or type(recommended) is not int or recommended <= 0 or reason is not None:
            # Apple reports zero before the first allocation; zero is valid at preload_baseline.
            _block("METAL_VALUES")


def validate_environment_receipt(receipt: dict[str, Any], *, target: dict[str, Any]) -> None:
    keys = {
        "schema_version", "platform", "chip", "physical_memory_bytes", "processor_count",
        "active_processor_count", "thermal_pre", "thermal_post", "low_power_mode",
        "power_source", "battery_state", "metal_registry_id", "macos_build", "xcode_build",
        "background_process_policy_sha256", "forbidden_process_count",
    }
    if set(receipt) != keys or receipt["schema_version"] != "butler.model-tier-b.environment.v2.8":
        _block("ENVIRONMENT_KEYS")
    if receipt["platform"] != "macOS" or receipt["chip"] != "Apple M3 Max":
        _block("TARGET_PROFILE")
    _positive(receipt["physical_memory_bytes"], "PHYSICAL_MEMORY")
    if receipt["physical_memory_bytes"] < target["minimum_physical_memory_bytes"]:
        _block("TARGET_MEMORY")
    if receipt["thermal_pre"] in {"serious", "critical"} or receipt["thermal_post"] in {"serious", "critical"}:
        _block("THERMAL_CRITICAL_ACCEPTED")
    if receipt["low_power_mode"] is not False or receipt["power_source"] != "AC Power":
        _block("POWER_STATE")
    if type(receipt["metal_registry_id"]) is not int or receipt["metal_registry_id"] <= 0:
        _block("METAL_RECEIPT")
    for key in ("background_process_policy_sha256",):
        if not isinstance(receipt[key], str) or not _SHA256.fullmatch(receipt[key]):
            _block("ENVIRONMENT_DIGEST")
    if receipt["forbidden_process_count"] != 0:
        _block("BACKGROUND_PROCESS")


def _positive(value: object, detail: str) -> None:
    if type(value) is not int or value <= 0:
        _block(detail)


def _block(detail: str) -> None:
    raise GateError(FailClass.ENVIRONMENT_MEMORY, detail, exit_code=ExitCode.ENVIRONMENT)
