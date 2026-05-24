from __future__ import annotations

from .base import make_sample_telemetry


def collect_windows_sample() -> dict:
    telemetry = make_sample_telemetry("windows", battery_source="Win32_Battery", evidence_class="ci_lab")
    telemetry["physical_windows_claim"] = False
    return telemetry
