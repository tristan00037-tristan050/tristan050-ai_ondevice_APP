from __future__ import annotations
import argparse
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

THERMAL_NORMAL = "normal"
THERMAL_HOT = "hot"
THERMAL_THROTTLED = "throttled"


def _safe_import_psutil():
    try:
        import psutil  # type: ignore
        return psutil, None
    except Exception as e:
        return None, str(e)


def _safe_import_torch():
    try:
        import torch  # type: ignore
        return torch, None
    except Exception as e:
        return None, str(e)


def _measure_cpu_usage(psutil_mod) -> float:
    """Avoid first-call 0.0 contamination by warming up once."""
    if psutil_mod is None:
        return 0.0
    try:
        _ = psutil_mod.cpu_percent(interval=None)
        value = float(psutil_mod.cpu_percent(interval=0.1))
        if value == 0.0:
            value = float(psutil_mod.cpu_percent(interval=0.2))
        return value
    except Exception:
        return 0.0


def collect_device_profile() -> dict[str, Any]:
    probe_errors: list[str] = []
    psutil, psutil_err = _safe_import_psutil()
    torch, torch_err = _safe_import_torch()
    if psutil_err:
        probe_errors.append(f"psutil_missing:{psutil_err}")
    if torch_err:
        probe_errors.append(f"torch_missing:{torch_err}")

    ram_avail_gb = 0.0
    cpu_cores = os.cpu_count() or 0
    cpu_usage_pct = 0.0
    battery_pct = None
    battery_plugged = None
    thermal_state = THERMAL_NORMAL
    cuda_available = 0
    vram_avail_gb = 0.0

    if psutil is not None:
        try:
            ram_avail_gb = round(psutil.virtual_memory().available / (1024**3), 2)
        except Exception as e:
            probe_errors.append(f"ram_probe_failed:{e}")
        try:
            cpu_usage_pct = round(_measure_cpu_usage(psutil), 2)
        except Exception as e:
            probe_errors.append(f"cpu_probe_failed:{e}")
        try:
            bat = psutil.sensors_battery()
            if bat is not None:
                battery_pct = int(bat.percent)
                battery_plugged = 1 if bat.power_plugged else 0
        except Exception as e:
            probe_errors.append(f"battery_probe_failed:{e}")

    if torch is not None:
        try:
            if torch.cuda.is_available():
                cuda_available = 1
                free_bytes, _total_bytes = torch.cuda.mem_get_info()
                vram_avail_gb = round(free_bytes / (1024**3), 2)
        except Exception as e:
            probe_errors.append(f"cuda_probe_failed:{e}")

    if cpu_usage_pct > 95:
        thermal_state = THERMAL_THROTTLED
    elif cpu_usage_pct > 85:
        thermal_state = THERMAL_HOT

    if ram_avail_gb < 6:
        recommendation = "light"
    elif cuda_available and vram_avail_gb < 8:
        recommendation = "light"
    elif battery_pct is not None and battery_plugged == 0 and battery_pct < 20:
        recommendation = "light"
    elif cpu_usage_pct > 80:
        recommendation = "light"
    elif thermal_state in {THERMAL_HOT, THERMAL_THROTTLED}:
        recommendation = "light"
    else:
        recommendation = "high"

    return {
        "ok": 1,
        "ram_avail_gb": ram_avail_gb,
        "cpu_cores": int(cpu_cores),
        "cpu_usage_pct": cpu_usage_pct,
        "battery_pct": battery_pct,
        "battery_plugged": battery_plugged,
        "cuda_available": int(cuda_available),
        "vram_avail_gb": vram_avail_gb,
        "thermal_state": thermal_state,
        "recommendation": recommendation,
        "probe_errors": probe_errors,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }


def print_device_profile(profile: dict[str, Any]) -> None:
    print("DEVICE_PROFILE_OK=1")
    print(f"DEVICE_RAM_AVAIL_GB={profile['ram_avail_gb']}")
    print(f"DEVICE_CPU_CORES={profile['cpu_cores']}")
    print(f"DEVICE_CPU_USAGE_PCT={profile['cpu_usage_pct']}")
    print(f"DEVICE_BATTERY_PCT={profile['battery_pct'] if profile.get('battery_pct') is not None else -1}")
    print(f"DEVICE_BATTERY_PLUGGED={profile['battery_plugged'] if profile.get('battery_plugged') is not None else -1}")
    print(f"DEVICE_CUDA_AVAILABLE={profile['cuda_available']}")
    print(f"DEVICE_VRAM_AVAIL_GB={profile['vram_avail_gb']}")
    print(f"DEVICE_THERMAL_STATE={profile['thermal_state']}")
    print(f"DEVICE_PROFILE_RECOMMENDATION={profile['recommendation']}")
    if any(str(e).startswith('psutil_missing') for e in profile.get('probe_errors', [])):
        print("DEVICE_PROFILE_NOTE=psutil_not_installed_optional_features_disabled")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    profile = collect_device_profile()
    print_device_profile(profile)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
