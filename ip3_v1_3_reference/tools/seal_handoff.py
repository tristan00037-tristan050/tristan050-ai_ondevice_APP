#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path:
    sys.path.insert(0, str(ROOT_HINT))

from src.ip3.telemetry_schema import read_json, write_json

APPROVAL_BY_CLASS = {
    "ci_lab": "APPROVED_FOR_AI_ONDEVICE13_HANDOFF_CI_LAB",
    "vm_lab": "APPROVED_FOR_AI_ONDEVICE13_HANDOFF_VM_LAB",
    "physical_lab": "APPROVED_FOR_AI_ONDEVICE13_HANDOFF_PHYSICAL_WINDOWS_LAB",
}
WINDOWS_LABEL = {
    "ci_lab": "WINDOWS_REAL_TELEMETRY_OK_CI_LAB",
    "vm_lab": "WINDOWS_REAL_TELEMETRY_OK_VM_LAB",
    "physical_lab": "WINDOWS_REAL_TELEMETRY_OK_PHYSICAL_LAB",
}
ALL_PLATFORM_LABEL = {
    "ci_lab": "ALL_PLATFORM_TELEMETRY_OK_CI_LAB",
    "vm_lab": "ALL_PLATFORM_TELEMETRY_OK_VM_LAB",
    "physical_lab": "ALL_PLATFORM_TELEMETRY_OK_PHYSICAL_LAB",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Create sealed handoff evidence after gates pass.")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--approval-class", choices=["ci_lab", "vm_lab", "physical_lab"], required=True)
    ap.add_argument("--require-three-platforms", action="store_true", default=True)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    errors: List[str] = []
    windows_report_path = root / "evidence" / "gate_results" / "windows_real_telemetry_gate.json"
    all_report_path = root / "evidence" / "gate_results" / "all_platform_telemetry_gate.json"
    if not windows_report_path.exists():
        errors.append("missing windows gate report")
        windows = None
    else:
        windows = read_json(windows_report_path)
        if not windows.get("ok") or windows.get("ok_label") != WINDOWS_LABEL[args.approval_class]:
            errors.append(f"windows gate must pass with {WINDOWS_LABEL[args.approval_class]}")
    if not all_report_path.exists():
        errors.append("missing all-platform gate report")
        allp = None
    else:
        allp = read_json(all_report_path)
        if not allp.get("ok") or allp.get("ok_label") != ALL_PLATFORM_LABEL[args.approval_class]:
            errors.append(f"all-platform gate must pass with {ALL_PLATFORM_LABEL[args.approval_class]}")
        if args.require_three_platforms:
            required = set(allp.get("required_platforms", []))
            observed = set(allp.get("observed_platforms", []))
            if required != {"linux", "darwin", "windows"} or observed != {"linux", "darwin", "windows"}:
                errors.append("three-platform handoff requires linux,darwin,windows observed")
    if args.approval_class == "physical_lab":
        if allp and allp.get("class_by_platform", {}).get("windows") != "physical_lab":
            errors.append("physical handoff requires windows physical_lab evidence")
    if args.approval_class != "physical_lab":
        # Explicitly do not allow low-level evidence to write the physical approval status.
        pass
    if errors:
        for err in errors:
            print(f"SEALED_HANDOFF_FAIL {err}", file=sys.stderr)
        return 2
    approval = APPROVAL_BY_CLASS[args.approval_class]
    payload: Dict[str, Any] = {
        "sealed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stage": "ip3_v1_3_windows_telemetry_strict_gate",
        "approval_class": args.approval_class,
        "approval_status": approval,
        "production_approved": False,
        "physical_windows_approved": args.approval_class == "physical_lab",
        "windows_gate_label": WINDOWS_LABEL[args.approval_class],
        "all_platform_gate_label": ALL_PLATFORM_LABEL[args.approval_class],
        "raw_prompt_recorded": False,
        "raw_user_text_recorded": False,
        "raw_log_recorded": False,
        "source_gate_reports": [
            "evidence/gate_results/windows_real_telemetry_gate.json",
            "evidence/gate_results/all_platform_telemetry_gate.json",
        ],
        "next_steps_not_claimed": [
            "production deployment",
            "actual Butler app production hook",
            "IP2 production PEP bridge",
            "IP1 forward_verified=true unless v5.4 evidence is supplied",
            "Product Candidate full replay unless separate live replay evidence is supplied",
        ],
    }
    out = root / "evidence" / f"sealed_handoff_{args.approval_class}.json"
    write_json(out, payload)
    if args.approval_class == "ci_lab":
        write_json(root / "evidence" / "sealed_handoff_ci_lab.json", payload)
    print(approval)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
