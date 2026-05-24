#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path:
    sys.path.insert(0, str(ROOT_HINT))

from src.ip3.telemetry_schema import validate_telemetry_file, write_json

LABEL_BY_CLASS = {
    "ci_lab": "WINDOWS_REAL_TELEMETRY_OK_CI_LAB",
    "vm_lab": "WINDOWS_REAL_TELEMETRY_OK_VM_LAB",
    "physical_lab": "WINDOWS_REAL_TELEMETRY_OK_PHYSICAL_LAB",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate Windows telemetry and emit evidence-class-specific OK labels.")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--expected-evidence-class", choices=["ci_lab", "vm_lab", "physical_lab"], required=True)
    ap.add_argument("--require-battery-present", action="store_true", help="Use for physical Windows notebook validation.")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    evidence_path = root / "evidence" / "real_telemetry_windows.json"
    require_physical = args.expected_evidence_class == "physical_lab"
    result = validate_telemetry_file(
        evidence_path,
        expected_platform="windows",
        expected_evidence_class=args.expected_evidence_class,
        strict_core=True,
        require_physical_windows=require_physical,
        require_battery_present=require_physical or args.require_battery_present,
    )
    report: Dict[str, Any] = {
        "gate": "windows_real_telemetry_gate",
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "expected_evidence_class": args.expected_evidence_class,
        "evidence_path": "evidence/real_telemetry_windows.json",
        "ok": result.ok,
        "result": result.as_dict(),
        "ok_label": LABEL_BY_CLASS[args.expected_evidence_class] if result.ok else None,
    }
    write_json(root / "evidence" / "gate_results" / "windows_real_telemetry_gate.json", report)
    if not result.ok:
        for err in result.errors:
            print(f"WINDOWS_REAL_TELEMETRY_GATE_FAIL {err}", file=sys.stderr)
        return 2
    print(LABEL_BY_CLASS[args.expected_evidence_class])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
