#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT_HINT = Path(__file__).resolve().parents[1]
if str(ROOT_HINT) not in sys.path: sys.path.insert(0, str(ROOT_HINT))
from src.ip3.bridges import build_ip1_model_registry_from_status, simulate_ip2_pep_contract
from src.ip3.latency import measure_ms
from src.ip3.routing_engine import RoutingEngine
from src.ip3.user_context import UserContext
from tools._sample_telemetry import sample_linux_telemetry

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    telemetry = sample_linux_telemetry()
    context = UserContext.from_metadata(task_type="analysis", urgency="normal", accuracy_requirement="high", data_sensitivity="Internal", request_fingerprint_seed="latency")
    policy = simulate_ip2_pep_contract("Internal").as_policy_decision()
    engine = RoutingEngine(build_ip1_model_registry_from_status({"forward_verified": False}))
    stats = measure_ms(lambda: engine.decide(telemetry=telemetry, context=context, ip2_policy_decision=policy), iterations)
    # Conservative budget for pure Python in CI; this is a routing decision budget, not model inference.
    ok = stats["p95_ms"] <= 15.0 and stats["p99_ms"] <= 40.0
    report = {"gate": "routing_latency_gate", "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "ok": ok, "ok_label": "ROUTING_LATENCY_BUDGET_OK" if ok else None, "budget": {"p95_ms": 15.0, "p99_ms": 40.0}, **stats}
    p = root / "evidence" / "sample_replay" / "routing_latency_gate.json"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    if not ok:
        print(f"ROUTING_LATENCY_BUDGET_FAIL p95_ms={stats['p95_ms']} p99_ms={stats['p99_ms']}", file=sys.stderr); return 2
    print(f"ROUTING_LATENCY_BUDGET_OK p50_ms={stats['p50_ms']} p95_ms={stats['p95_ms']} p99_ms={stats['p99_ms']}")
    return 0
if __name__ == "__main__": raise SystemExit(main())
