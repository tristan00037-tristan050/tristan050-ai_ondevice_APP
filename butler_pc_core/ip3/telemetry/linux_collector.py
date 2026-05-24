from __future__ import annotations

from .base import make_sample_telemetry


def collect_linux_sample() -> dict:
    return make_sample_telemetry("linux", battery_source="upower", evidence_class="ci_lab")
