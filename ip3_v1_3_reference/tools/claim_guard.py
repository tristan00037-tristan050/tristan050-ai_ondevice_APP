#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path
from typing import Any, List

FORBIDDEN_PRODUCTION_STATUSES = {"APPROVED_FOR_PRODUCTION", "PRODUCTION_RELEASE_OK", "FULL_DEPLOYMENT_OK"}
MUST_BE_FALSE = [
    "operational_full_claimed", "production_hook_deployed", "physical_lab_claimed", "production_claimed",
    "all_platform_strict_pass_claimed", "product_candidate_full_replay_claimed", "live_app_hook_deployed",
    "ip2_pep_live_bridge_deployed", "local_1_7b_forward_verified", "release_claim_allowed"
]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def gate_ok(root: Path, rel: str, label_prefix: str) -> bool:
    p = root / rel
    if not p.exists():
        return False
    try:
        data = load(p)
    except Exception:
        return False
    return bool(data.get("ok")) and str(data.get("ok_label", "")).startswith(label_prefix)


def scan_evidence_text(root: Path) -> list[str]:
    errors: list[str] = []
    ev = root / "evidence"
    if not ev.exists():
        return errors
    for p in ev.rglob("*.json"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        rel = p.relative_to(root)
        for status in FORBIDDEN_PRODUCTION_STATUSES:
            if status in text:
                errors.append(f"forbidden production status {status} in {rel}")
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    errors: List[str] = []
    state_names = ["evidence/v1_3_full_stack_state.json", "evidence/v1_3_ci_lab_state.json"]
    existing_state_names = [name for name in state_names if (root / name).exists()]
    if not existing_state_names:
        errors.append("missing v1.3 state file")
    for state_name in existing_state_names:
        p = root / state_name
        state = load(p)
        for key in MUST_BE_FALSE:
            if state.get(key) is not False:
                errors.append(f"{state_name}:{key} must be false, actual={state.get(key)!r}")
        if state.get("approval_status") not in {"NOT_CLAIMED", "not_claimed", None}:
            errors.append(f"{state_name}:approval_status must remain NOT_CLAIMED in base package")
        if state.get("product_candidate_full_replay_harness_validated_sample") is True and state.get("product_candidate_full_replay_claimed") is True:
            errors.append("sample product replay harness cannot set product_candidate_full_replay_claimed=true")
        if state.get("live_app_hook_harness_validated_sample") is True and state.get("production_hook_deployed") is True:
            errors.append("sample live hook harness cannot set production_hook_deployed=true")
        classes = state.get("windows_telemetry_validated_by_class", {})
        if isinstance(classes, dict):
            if classes.get("physical_lab") is True and not gate_ok(root, "evidence/gate_results/windows_real_telemetry_gate.json", "WINDOWS_REAL_TELEMETRY_OK_PHYSICAL_LAB"):
                errors.append("physical_lab Windows validation cannot be true without physical_lab gate report")
            if classes.get("production") is True:
                errors.append("production Windows validation cannot be true in v1.3 lab package")
    # CI_LAB handoff approval requires CI gate reports if present.
    for p in (root / "evidence").glob("sealed_handoff*.json") if (root / "evidence").exists() else []:
        data = load(p)
        status = data.get("approval_status")
        if status in {None, "NOT_CLAIMED", "not_claimed"}:
            continue
        if status == "APPROVED_FOR_AI_ONDEVICE13_HANDOFF_CI_LAB":
            if data.get("approval_class") != "ci_lab": errors.append("CI handoff approval requires approval_class=ci_lab")
            if not gate_ok(root, "evidence/gate_results/all_platform_telemetry_gate.json", "ALL_PLATFORM_TELEMETRY_OK_CI_LAB"):
                errors.append("CI handoff approval requires all-platform CI gate report")
        elif status == "APPROVED_FOR_AI_ONDEVICE13_HANDOFF_PHYSICAL_WINDOWS_LAB":
            if data.get("approval_class") != "physical_lab": errors.append("physical handoff approval requires approval_class=physical_lab")
            if not gate_ok(root, "evidence/gate_results/windows_real_telemetry_gate.json", "WINDOWS_REAL_TELEMETRY_OK_PHYSICAL_LAB"):
                errors.append("physical approval requires physical Windows telemetry gate")
        else:
            errors.append(f"unknown or forbidden approval_status={status!r}")
        if data.get("production_approved") is not False:
            errors.append("production_approved must be false")
    errors.extend(scan_evidence_text(root))
    if errors:
        for e in errors:
            print(f"CLAIM_GUARD_FAIL {e}", file=sys.stderr)
        return 2
    print("CLAIM_GUARD_OK")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
