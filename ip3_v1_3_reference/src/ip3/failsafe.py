from __future__ import annotations

from typing import Any, Mapping

FAILSAFE_SCENARIOS = (
    "telemetry_missing",
    "ip2_policy_denied",
    "ip1_forward_not_verified",
    "thermal_critical",
    "network_unavailable",
    "restricted_not_executable",
)


def inject_failure_scenario(name: str, base_event: Mapping[str, Any], telemetry: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if name not in FAILSAFE_SCENARIOS:
        raise ValueError(f"unknown fail-safe scenario: {name}")
    event = dict(base_event)
    tel = {**telemetry, "measurements": dict(telemetry.get("measurements", {}))}
    if name == "telemetry_missing":
        tel["measurements"] = {}
    elif name == "ip2_policy_denied":
        event["ip2_allow"] = False
    elif name == "ip1_forward_not_verified":
        event["data_sensitivity"] = "Restricted"
    elif name == "thermal_critical":
        tel["measurements"]["thermal"] = {"status": "ok", "source": "injection", "thermal_state": "critical"}
    elif name == "network_unavailable":
        tel["measurements"]["network"] = {"status": "failed", "source": "injection", "network_available": False, "reason": "injected"}
    elif name == "restricted_not_executable":
        event["data_sensitivity"] = "Restricted"
    return event, tel
