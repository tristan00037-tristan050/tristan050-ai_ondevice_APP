#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path: sys.path.insert(0, str(ROOT_HINT))
from src.ip3.bridges import build_ip1_model_registry_from_status
from src.ip3.live_hook import ButlerAppSourceRoutingHook
from src.ip3.routing_engine import RoutingEngine
from tools._sample_telemetry import sample_linux_telemetry

def build_event(i: int) -> dict:
    return {
        "task_type": ["coding", "analysis", "summarization", "admin"][i % 4],
        "urgency": ["low", "normal", "high", "critical"][i % 4],
        "accuracy_requirement": ["medium", "high", "critical"][i % 3],
        "data_sensitivity": ["Restricted", "Confidential", "Internal", "Public"][i % 4],
        "request_seed": f"pc-full-replay-{i}",
        "ip2_allow": i % 31 != 0,
        "residual_pii": 1 if i % 97 == 0 else 0
    }

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    hook = ButlerAppSourceRoutingHook(RoutingEngine(build_ip1_model_registry_from_status({"forward_verified": False}), external_api_enabled=False))
    telemetry = sample_linux_telemetry()
    counts = {"routed": 0, "blocked": 0, "failed_closed": 0, "fallback": 0}
    for i in range(count):
        out = hook.handle_event(build_event(i), telemetry)
        state = out["decision"]["routing_state"]
        counts[state] = counts.get(state, 0) + 1
    # In current forward_verified=false state, restricted local cases must not become executable routed.
    ok = counts["failed_closed"] > 0 and counts["blocked"] > 0 and sum(counts.values()) == count
    report = {"gate": "product_candidate_full_replay_gate", "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "ok": ok, "ok_label": "PRODUCT_CANDIDATE_FULL_REPLAY_OK_SAMPLE" if ok else None, "evidence_class": "sample", "real_full_replay_claimed": False, "event_count": count, "state_counts": counts}
    p = root / "evidence" / "sample_replay" / "product_candidate_full_replay_gate.json"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    if not ok:
        print("PRODUCT_CANDIDATE_FULL_REPLAY_FAIL", file=sys.stderr); return 2
    for state_name in ["v1_3_full_stack_state.json", "v1_3_ci_lab_state.json"]:
        sp = root / "evidence" / state_name
        if sp.exists():
            state = json.loads(sp.read_text(encoding="utf-8")); state["product_candidate_full_replay_harness_validated_sample"] = True; state["product_candidate_full_replay_claimed"] = False; sp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(f"PRODUCT_CANDIDATE_FULL_REPLAY_OK_SAMPLE events={count} real_full_replay_claimed=false")
    return 0
if __name__ == "__main__": raise SystemExit(main())
