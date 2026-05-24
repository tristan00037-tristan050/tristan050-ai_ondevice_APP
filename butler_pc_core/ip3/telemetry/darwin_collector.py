from __future__ import annotations

from .base import make_sample_telemetry


def collect_darwin_sample() -> dict:
    return make_sample_telemetry("darwin", battery_source="IOKit", evidence_class="ci_lab")
