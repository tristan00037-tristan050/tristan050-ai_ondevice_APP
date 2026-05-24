#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path: sys.path.insert(0, str(ROOT_HINT))
from src.ip3.bridges import simulate_ip2_pep_contract

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    cases = [simulate_ip2_pep_contract("Restricted", allow=True, residual_pii=0), simulate_ip2_pep_contract("Confidential", allow=True, residual_pii=1), simulate_ip2_pep_contract("Public", allow=False, residual_pii=0)]
    ok = cases[0].allow is True and cases[1].allow is False and cases[2].allow is False
    report = {"gate": "ip2_pep_live_bridge_gate", "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "ok": ok, "ok_label": "IP2_PEP_LIVE_BRIDGE_OK_SAMPLE", "evidence_class": "sample", "live_bridge_deployed": False, "cases": [c.__dict__ for c in cases]}
    p = root / "evidence" / "sample_replay" / "ip2_pep_bridge_gate.json"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    if not ok:
        print("IP2_PEP_LIVE_BRIDGE_FAIL", file=sys.stderr); return 2
    for state_name in ["v1_3_full_stack_state.json", "v1_3_ci_lab_state.json"]:
        sp = root / "evidence" / state_name
        if sp.exists():
            state = json.loads(sp.read_text(encoding="utf-8")); state["ip2_pep_contract_harness_validated_sample"] = True; state["ip2_pep_live_bridge_deployed"] = False; sp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print("IP2_PEP_LIVE_BRIDGE_OK_SAMPLE live_bridge_deployed=false residual_pii_blocking=true")
    return 0
if __name__ == "__main__": raise SystemExit(main())
