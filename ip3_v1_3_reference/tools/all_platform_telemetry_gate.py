#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path:
    sys.path.insert(0, str(ROOT_HINT))

from src.ip3.telemetry_schema import normalize_platform_name, validate_required_platform_files, write_json

LABEL_BY_LEVEL = {
    "ci_lab": "ALL_PLATFORM_TELEMETRY_OK_CI_LAB",
    "vm_lab": "ALL_PLATFORM_TELEMETRY_OK_VM_LAB",
    "physical_lab": "ALL_PLATFORM_TELEMETRY_OK_PHYSICAL_LAB",
}
WINDOWS_ONLY_LABEL_BY_LEVEL = {
    "ci_lab": "WINDOWS_ONLY_TELEMETRY_OK_CI_LAB",
    "vm_lab": "WINDOWS_ONLY_TELEMETRY_OK_VM_LAB",
    "physical_lab": "WINDOWS_ONLY_TELEMETRY_OK_PHYSICAL_LAB",
}


def parse_platform_class(items: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"platform evidence class override must be platform=class, actual={item!r}")
        platform, klass = item.split("=", 1)
        out[normalize_platform_name(platform)] = klass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Strict Darwin/Linux/Windows telemetry validator with separated approval levels.")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--require-platforms", default="linux,darwin,windows")
    ap.add_argument("--expected-evidence-class", choices=["ci_lab", "vm_lab", "physical_lab"], required=True)
    ap.add_argument("--platform-evidence-class", action="append", default=[], help="Override per platform, e.g. windows=vm_lab")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--require-battery-present", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    required = [normalize_platform_name(x) for x in args.require_platforms.split(",") if x.strip()]
    class_by_platform = {p: args.expected_evidence_class for p in required}
    class_by_platform.update(parse_platform_class(args.platform_evidence_class))

    require_physical_windows = class_by_platform.get("windows") == "physical_lab"
    ok, observed, missing, results = validate_required_platform_files(
        root,
        required,
        expected_class_by_platform=class_by_platform,
        strict_core=args.strict,
        require_physical_windows=require_physical_windows,
        require_battery_present=(require_physical_windows or args.require_battery_present),
    )
    platform_results = {k: v.as_dict() for k, v in results.items()}
    label = None
    if ok:
        if required == ["windows"]:
            label = WINDOWS_ONLY_LABEL_BY_LEVEL[args.expected_evidence_class]
        else:
            label = LABEL_BY_LEVEL[args.expected_evidence_class]
    report = {
        "gate": "all_platform_telemetry_gate",
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "required_platforms": required,
        "observed_platforms": observed,
        "missing_platforms": missing,
        "expected_evidence_class": args.expected_evidence_class,
        "class_by_platform": class_by_platform,
        "strict_core": bool(args.strict),
        "ok": ok,
        "ok_label": label,
        "platform_results": platform_results,
    }
    write_json(root / "evidence" / "gate_results" / "all_platform_telemetry_gate.json", report)
    if not ok:
        print(f"ALL_PLATFORM_TELEMETRY_GATE_FAIL platforms_missing={missing} observed={observed}", file=sys.stderr)
        for platform, result in platform_results.items():
            for err in result.get("errors", []):
                print(f"ALL_PLATFORM_TELEMETRY_GATE_FAIL platform={platform} {err}", file=sys.stderr)
        return 2
    print(label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
