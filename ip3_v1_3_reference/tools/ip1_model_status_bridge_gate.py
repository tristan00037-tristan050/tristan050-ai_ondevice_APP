#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path: sys.path.insert(0, str(ROOT_HINT))
from src.ip3.bridges import build_ip1_model_registry_from_status

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    registry = build_ip1_model_registry_from_status({"forward_verified": False})
    local = registry["local_1_7b"]
    ok = local.forward_verified is False and local.routing_executable is False and local.status == "artifact_sealed"
    report = {"gate": "ip1_model_status_bridge_gate", "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "ok": ok, "ok_label": "IP1_MODEL_STATUS_BRIDGE_OK", "forward_verified": False, "routing_executable": False, "model_status": local.status}
    p = root / "evidence" / "sample_replay" / "ip1_model_status_bridge_gate.json"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    if not ok:
        print("IP1_MODEL_STATUS_BRIDGE_FAIL", file=sys.stderr); return 2
    for state_name in ["v1_3_full_stack_state.json", "v1_3_ci_lab_state.json"]:
        sp = root / "evidence" / state_name
        if sp.exists():
            state = json.loads(sp.read_text(encoding="utf-8")); state["ip1_model_status_bridge_ready"] = True; state["local_1_7b_forward_verified"] = False; sp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print("IP1_MODEL_STATUS_BRIDGE_OK forward_verified=false routing_executable=false")
    return 0
if __name__ == "__main__": raise SystemExit(main())
