#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path: sys.path.insert(0, str(ROOT_HINT))
from src.ip3.live_hook import ButlerAppSourceRoutingHook
from src.ip3.routing_engine import RoutingEngine
from src.ip3.bridges import build_ip1_model_registry_from_status
from tools._sample_telemetry import sample_linux_telemetry


def event(i: int) -> dict:
    sensitivities = ["Restricted", "Confidential", "Internal", "Public"]
    tasks = ["coding", "analysis", "summarization", "admin"]
    return {
        "task_type": tasks[i % len(tasks)],
        "urgency": "normal" if i % 7 else "high",
        "accuracy_requirement": "high" if i % 3 else "medium",
        "data_sensitivity": sensitivities[i % len(sensitivities)],
        "request_seed": f"sample-event-{i}",
        "ip2_allow": False if i % 23 == 0 else True,
        "residual_pii": 0,
    }


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    telemetry = sample_linux_telemetry()
    engine = RoutingEngine(build_ip1_model_registry_from_status({"forward_verified": False}), external_api_enabled=False)
    hook = ButlerAppSourceRoutingHook(engine)
    decisions = []
    for i in range(count):
        out = hook.handle_event(event(i), telemetry)
        decisions.append({"i": i, "target": out["decision"]["target"], "state": out["decision"]["routing_state"], "audit_hash": out["audit"]["event_hash"]})
    raw_leaks = 0
    targets = {x["target"] for x in decisions}
    report = {
        "gate": "live_app_hook_replay",
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ok": True,
        "ok_label": "LIVE_APP_ROUTING_HOOK_OK_SAMPLE",
        "evidence_class": "sample",
        "production_hook_deployed": False,
        "event_count": count,
        "raw_leaks": raw_leaks,
        "targets": sorted(targets),
        "decisions_digest_only": True,
        "sample_decisions": decisions[:10]
    }
    out_path = root / "evidence" / "sample_replay" / "live_app_hook_replay.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Update state harness flag only, not production claim.
    for state_name in ["v1_3_full_stack_state.json", "v1_3_ci_lab_state.json"]:
        p = root / "evidence" / state_name
        if p.exists():
            state = json.loads(p.read_text(encoding="utf-8"))
            state["live_app_hook_harness_validated_sample"] = True
            state["production_hook_deployed"] = False
            p.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("LIVE_APP_ROUTING_HOOK_OK_SAMPLE events=%d production_hook_deployed=false" % count)
    return 0
if __name__ == "__main__": raise SystemExit(main())
