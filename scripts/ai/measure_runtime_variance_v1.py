#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
from pathlib import Path

SAMPLES_PATH = Path("tmp/runtime_variance_samples.json")
OUT_PATH = Path("tmp/runtime_variance_summary.json")


def main() -> None:
    data = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))

    if len(data) < 30:
        raise RuntimeError(f"RUNTIME_VARIANCE_SAMPLE_COUNT_TOO_LOW:{len(data)}")

    lat = [x["latency_ms"] for x in data]
    ttft = [x["ttft_ms"] for x in data]
    dps = [x["decode_tps"] for x in data]
    rss = [x["rss_peak_mb"] for x in data]
    energy = [x["energy_proxy"] for x in data]
    thermal = [x["thermal_degradation_pct"] for x in data]

    def pct(values: list[float], p: int) -> float:
        values = sorted(values)
        idx = max(0, min(len(values) - 1, int((p / 100.0) * len(values)) - 1))
        return values[idx]

    summary = {
        "sample_count": len(data),
        "latency_mean_ms": statistics.mean(lat),
        "latency_std_ms": statistics.pstdev(lat) if len(lat) > 1 else 0.0,
        "latency_p50_ms": pct(lat, 50),
        "latency_p95_ms": pct(lat, 95),
        "latency_p99_ms": pct(lat, 99),
        "ttft_mean_ms": statistics.mean(ttft),
        "ttft_std_ms": statistics.pstdev(ttft) if len(ttft) > 1 else 0.0,
        "decode_tps_mean": statistics.mean(dps),
        "decode_tps_min": min(dps),
        "rss_peak_mean_mb": statistics.mean(rss),
        "rss_peak_max_mb": max(rss),
        "energy_proxy_mean": statistics.mean(energy),
        "thermal_degradation_pct": statistics.mean(thermal),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("RUNTIME_VARIANCE_SUMMARY_WRITTEN=1")


if __name__ == "__main__":
    main()
