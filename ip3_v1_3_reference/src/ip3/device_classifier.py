from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

@dataclass(frozen=True)
class DeviceClassification:
    device_class: str
    trust_level: str
    score: int
    reasons: tuple[str, ...]


def _gb(bytes_value: int | float | None) -> float:
    if not bytes_value:
        return 0.0
    return float(bytes_value) / (1024 ** 3)


def classify_device(telemetry: Mapping[str, Any]) -> DeviceClassification:
    m = telemetry.get("measurements", {}) if isinstance(telemetry, Mapping) else {}
    reasons: list[str] = []
    score = 0

    cpu = m.get("cpu", {})
    mem = m.get("memory", {})
    batt = m.get("battery", {})
    therm = m.get("thermal", {})
    net = m.get("network", {})

    if cpu.get("status") == "ok" and int(cpu.get("logical_processors", 0)) >= 8:
        score += 25
    elif cpu.get("status") == "ok" and int(cpu.get("logical_processors", 0)) >= 4:
        score += 15
    else:
        reasons.append("cpu_limited")

    mem_gb = _gb(mem.get("total_bytes"))
    if mem.get("status") == "ok" and mem_gb >= 16:
        score += 25
    elif mem.get("status") == "ok" and mem_gb >= 8:
        score += 15
    else:
        reasons.append("memory_limited")

    if batt.get("status") in {"ok", "limited", "unavailable"}:
        # desktops or CI runners can be unavailable but not automatically untrusted.
        charge = batt.get("estimated_charge_remaining_percent")
        if isinstance(charge, (int, float)) and charge < 20:
            reasons.append("battery_low")
        else:
            score += 15
    else:
        reasons.append("battery_failed")

    thermal_state = str(therm.get("thermal_state", "unknown")).lower()
    if therm.get("status") in {"ok", "limited", "unavailable"} and thermal_state not in {"critical", "hot"}:
        score += 15
    else:
        reasons.append("thermal_risk")

    if net.get("status") == "ok" and net.get("network_available") is True:
        score += 20
    else:
        reasons.append("network_unavailable")

    if score >= 85:
        cls = "A"
    elif score >= 65:
        cls = "B"
    elif score >= 40:
        cls = "C"
    else:
        cls = "D"

    trust = "measured" if score >= 65 else "degraded"
    return DeviceClassification(device_class=cls, trust_level=trust, score=score, reasons=tuple(reasons))
