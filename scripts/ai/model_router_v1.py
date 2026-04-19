from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ai.device_profiler_v1 import collect_device_profile

REASON_CODES = {
    "forced_light", "forced_high", "ram_low", "vram_low", "battery_low",
    "cpu_busy", "thermal_hot", "ram_sufficient"
}


def route_model(profile: dict[str, Any], force: str | None = None) -> dict[str, Any]:
    pref = force or os.getenv("BUTLER_FORCE_MODEL")
    if pref == "light":
        primary = "light"
        reason = "forced_light"
    elif pref == "high":
        primary = "high"
        reason = "forced_high"
    elif float(profile.get("ram_avail_gb", 0)) < 6:
        primary = "light"
        reason = "ram_low"
    elif int(profile.get("cuda_available", 0)) == 1 and float(profile.get("vram_avail_gb", 0)) < 8:
        primary = "light"
        reason = "vram_low"
    elif profile.get("battery_pct") is not None and int(profile.get("battery_plugged") or 0) == 0 and int(profile.get("battery_pct") or 0) < 20:
        primary = "light"
        reason = "battery_low"
    elif float(profile.get("cpu_usage_pct", 0)) > 80:
        primary = "light"
        reason = "cpu_busy"
    elif str(profile.get("thermal_state", "normal")) in {"hot", "throttled"}:
        primary = "light"
        reason = "thermal_hot"
    else:
        primary = "high"
        reason = "ram_sufficient"

    selected = primary
    mismatch = 1 if profile.get("recommendation") and profile.get("recommendation") != primary else 0
    return {
        "ok": 1,
        "primary_selected": primary,
        "selected": selected,
        "reason_code": reason,
        "profile_used": 1,
        "fallback_used": 0,
        "fallback_reason": None,
        "mismatch_with_recommendation": mismatch,
    }


def apply_fallback(router_result: dict[str, Any], high_model_load_ok: bool) -> dict[str, Any]:
    out = dict(router_result)
    if out["primary_selected"] == "high" and not high_model_load_ok:
        out["selected"] = "light"
        out["fallback_used"] = 1
        out["fallback_reason"] = "high_model_load_failed"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--force-light", action="store_true")
    grp.add_argument("--force-high", action="store_true")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    force = "light" if args.force_light else ("high" if args.force_high else None)
    profile = collect_device_profile()
    routed = route_model(profile, force=force)
    print("MODEL_ROUTER_OK=1")
    print(f"MODEL_ROUTER_SELECTED={routed['selected']}")
    print(f"MODEL_ROUTER_REASON_CODE={routed['reason_code']}")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(routed, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
