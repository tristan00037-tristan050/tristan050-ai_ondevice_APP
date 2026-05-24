#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path: sys.path.insert(0, str(ROOT_HINT))
from src.ip3.bridges import build_ip1_model_registry_from_status
from src.ip3.failsafe import FAILSAFE_SCENARIOS, inject_failure_scenario
from src.ip3.live_hook import ButlerAppSourceRoutingHook
from src.ip3.routing_engine import RoutingEngine
from tools._sample_telemetry import sample_linux_telemetry

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    base_event = {"task_type": "analysis", "urgency": "high", "accuracy_requirement": "high", "data_sensitivity": "Restricted", "request_seed": "failsafe", "ip2_allow": True, "residual_pii": 0}
    telemetry = sample_linux_telemetry()
    hook = ButlerAppSourceRoutingHook(RoutingEngine(build_ip1_model_registry_from_status({"forward_verified": False})))
    results = []
    for name in FAILSAFE_SCENARIOS:
        ev, tel = inject_failure_scenario(name, base_event, telemetry)
        out = hook.handle_event(ev, tel)
        state = out["decision"]["routing_state"]
        target = out["decision"]["target"]
        results.append({"scenario": name, "state": state, "target": target})
    ok = len(results) == 6 and all(r["target"] == "blocked" or r["state"] in {"blocked", "failed_closed", "fallback"} for r in results)
    report = {"gate": "failsafe_live_injection_gate", "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "ok": ok, "ok_label": "FAIL_SAFE_LIVE_INJECTION_OK_SAMPLE" if ok else None, "evidence_class": "sample", "scenarios": results}
    p = root / "evidence" / "sample_replay" / "failsafe_live_injection_gate.json"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    if not ok:
        print("FAIL_SAFE_LIVE_INJECTION_FAIL", file=sys.stderr); return 2
    print("FAIL_SAFE_LIVE_INJECTION_OK_SAMPLE scenarios=6")
    return 0
if __name__ == "__main__": raise SystemExit(main())
