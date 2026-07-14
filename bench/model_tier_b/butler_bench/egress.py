from __future__ import annotations

import re
from typing import Any

from .canonical import canonical_sha256
from .errors import ExitCode, FailClass, GateError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEYS = {
    "schema_version", "controller_type", "controller_binary_sha256", "policy_sha256",
    "activation_monotonic_ns", "deactivation_monotonic_ns", "target_pid_set",
    "child_process_scope_verified", "failure_default", "denied_attempt_count",
    "allowed_attempt_count", "native_ipv4_probe", "native_ipv6_probe", "dns_probe",
    "https_probe", "subprocess_probe", "receipt_subject_sha256",
}
_CONTROLLERS = {
    "NETWORK_EXTENSION_CONTENT_FILTER",
    "DEDICATED_USER_OS_DENY_CONTROLLER",
    "EXTERNAL_DENY_ALL_NETWORK",
}


def validate_egress_receipt(
    receipt: dict[str, Any],
    *,
    policy: dict[str, Any],
    expected_pid_set: list[int],
    run_start_ns: int,
    run_end_ns: int,
) -> str:
    if set(receipt) != _KEYS or receipt["schema_version"] != "butler.model-tier-b.os-egress.v2.8":
        _block("EGRESS_KEYS")
    subject = receipt["receipt_subject_sha256"]
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_subject_sha256"}
    if not isinstance(subject, str) or canonical_sha256(unsigned) != subject:
        _block("EGRESS_SUBJECT")
    controller = receipt["controller_type"]
    if controller not in _CONTROLLERS:
        _block("EGRESS_CONTROLLER_TYPE")
    profiles = policy.get("approved_controller_profiles")
    if not isinstance(profiles, dict) or controller not in profiles:
        _block("EGRESS_CONTROLLER_NOT_APPROVED")
    approved = profiles[controller]
    if not isinstance(approved, dict) or set(approved) != {"binary_sha256", "policy_sha256"}:
        _block("EGRESS_PROFILE")
    for key in ("controller_binary_sha256", "policy_sha256"):
        if not isinstance(receipt[key], str) or not _SHA256.fullmatch(receipt[key]):
            _block("EGRESS_DIGEST")
    if receipt["controller_binary_sha256"] != approved["binary_sha256"] or receipt["policy_sha256"] != approved["policy_sha256"]:
        _block("EGRESS_PROFILE_DIGEST")
    if not isinstance(run_start_ns, int) or not isinstance(run_end_ns, int) or not 0 < run_start_ns < run_end_ns:
        _block("RUN_INTERVAL")
    if receipt["activation_monotonic_ns"] > run_start_ns or receipt["deactivation_monotonic_ns"] < run_end_ns:
        _block("CONTROLLER_INTERVAL_GAP")
    if receipt["activation_monotonic_ns"] <= 0 or receipt["deactivation_monotonic_ns"] <= receipt["activation_monotonic_ns"]:
        _block("CONTROLLER_INTERVAL")
    if expected_pid_set != sorted(set(expected_pid_set)) or any(type(pid) is not int or pid <= 0 for pid in expected_pid_set):
        _block("EXPECTED_PID_SET")
    if receipt["target_pid_set"] != expected_pid_set:
        _block("TARGET_PID_SET")
    if receipt["child_process_scope_verified"] is not True or receipt["failure_default"] != "DENY":
        _block("CONTROLLER_SCOPE_OR_DEFAULT")
    probes = ("native_ipv4_probe", "native_ipv6_probe", "dns_probe", "https_probe", "subprocess_probe")
    if any(receipt[name] != "DENIED" for name in probes):
        _block("EGRESS_PROBE_ALLOWED")
    if receipt["allowed_attempt_count"] != 0 or policy.get("allowed_outbound_attempts") != 0:
        _block("EGRESS_ALLOWED_COUNT")
    if not isinstance(receipt["denied_attempt_count"], int) or receipt["denied_attempt_count"] < len(probes):
        _block("EGRESS_DENIED_COUNT")
    return subject


def _block(detail: str) -> None:
    raise GateError(FailClass.EGRESS, detail, exit_code=ExitCode.SECURITY)
