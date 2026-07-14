from __future__ import annotations

import re
from typing import Any

from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEYS = {
    "schema_version", "candidate_A", "candidate_B", "worker_pid_A", "worker_pid_B",
    "parent_observed_pid_set", "worker_executable_sha256_A", "worker_executable_sha256_B",
    "loaded_start_ns_A", "loaded_end_ns_A", "loaded_start_ns_B", "loaded_end_ns_B",
    "inference_intervals_A", "inference_intervals_B", "model_pre_sha256_A",
    "model_post_sha256_A", "model_pre_sha256_B", "model_post_sha256_B",
    "observer_stream_sha256", "policy_bypass_count", "oom_count", "sampler_error_count",
    "swap_delta_bytes",
}


def validate_dual_resident(receipt: dict[str, Any], policy: dict[str, Any]) -> int:
    if set(receipt) != _KEYS or receipt["schema_version"] != "butler.model-tier-b.dual-resident.v2.8":
        _block("DUAL_KEYS")
    a, b = receipt["candidate_A"], receipt["candidate_B"]
    candidate_keys = {"variant_id", "model_manifest_sha256", "runtime_config_sha256"}
    if not isinstance(a, dict) or not isinstance(b, dict) or set(a) != candidate_keys or set(b) != candidate_keys:
        _block("DUAL_CANDIDATE_KEYS")
    if a["variant_id"] == b["variant_id"] or a["model_manifest_sha256"] == b["model_manifest_sha256"]:
        _block("SAME_MODEL_BOTH_CANDIDATES")
    for item in (a, b):
        for key in ("model_manifest_sha256", "runtime_config_sha256"):
            if not isinstance(item[key], str) or not _SHA256.fullmatch(item[key]):
                _block("DUAL_IDENTITY_DIGEST")
    pid_a, pid_b = receipt["worker_pid_A"], receipt["worker_pid_B"]
    if type(pid_a) is not int or type(pid_b) is not int or pid_a <= 0 or pid_b <= 0 or pid_a == pid_b:
        _block("DUAL_PID")
    if receipt["parent_observed_pid_set"] != sorted([pid_a, pid_b]):
        _block("DUAL_PARENT_PID_SCOPE")
    for key in ("worker_executable_sha256_A", "worker_executable_sha256_B", "observer_stream_sha256"):
        if not isinstance(receipt[key], str) or not _SHA256.fullmatch(receipt[key]):
            _block("DUAL_EXECUTABLE_OR_STREAM_DIGEST")
    clocks = [receipt[key] for key in ("loaded_start_ns_A", "loaded_end_ns_A", "loaded_start_ns_B", "loaded_end_ns_B")]
    if any(type(value) is not int or value <= 0 for value in clocks):
        _block("DUAL_CLOCK")
    if receipt["loaded_start_ns_A"] >= receipt["loaded_end_ns_A"] or receipt["loaded_start_ns_B"] >= receipt["loaded_end_ns_B"]:
        _block("DUAL_INTERVAL")
    overlap_start = max(receipt["loaded_start_ns_A"], receipt["loaded_start_ns_B"])
    overlap_end = min(receipt["loaded_end_ns_A"], receipt["loaded_end_ns_B"])
    overlap = overlap_end - overlap_start
    minimum = policy.get("min_co_residency_seconds")
    if type(minimum) is not int or minimum <= 0 or overlap < minimum * 1_000_000_000:
        _block("DUAL_OVERLAP")
    for key in ("inference_intervals_A", "inference_intervals_B"):
        intervals = receipt[key]
        if not isinstance(intervals, list) or not intervals:
            _block("DUAL_INFERENCE_MISSING")
        valid_overlap = False
        for interval in intervals:
            if not isinstance(interval, dict) or set(interval) != {"start_ns", "end_ns", "fixture_id", "stream_sha256"}:
                _block("DUAL_INFERENCE_KEYS")
            if type(interval["start_ns"]) is not int or type(interval["end_ns"]) is not int or interval["start_ns"] >= interval["end_ns"]:
                _block("DUAL_INFERENCE_CLOCK")
            if not isinstance(interval["fixture_id"], str) or not interval["fixture_id"]:
                _block("DUAL_FIXTURE")
            if not isinstance(interval["stream_sha256"], str) or not _SHA256.fullmatch(interval["stream_sha256"]):
                _block("DUAL_STREAM_DIGEST")
            valid_overlap |= interval["start_ns"] < overlap_end and interval["end_ns"] > overlap_start
        if not valid_overlap:
            _block("NO_INFERENCE_OVERLAP")
    bindings = (
        ("model_pre_sha256_A", "model_post_sha256_A", a["model_manifest_sha256"]),
        ("model_pre_sha256_B", "model_post_sha256_B", b["model_manifest_sha256"]),
    )
    for pre_key, post_key, expected in bindings:
        if receipt[pre_key] != expected or receipt[post_key] != expected:
            _block("DUAL_MODEL_PRE_POST")
    for key in ("policy_bypass_count", "oom_count", "sampler_error_count"):
        if receipt[key] != 0:
            _block("DUAL_RUNTIME_COUNTER")
    max_swap = policy.get("max_swap_delta_bytes", 0)
    if type(receipt["swap_delta_bytes"]) is not int or receipt["swap_delta_bytes"] < 0 or receipt["swap_delta_bytes"] > max_swap:
        _block("DUAL_SWAP_DELTA")
    return overlap


def _block(detail: str) -> None:
    raise GateError(FailClass.DUAL_RESIDENT, detail, exit_code=ExitCode.ENVIRONMENT)
