#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path

REQUIRED_TYPES = {"DeviceTelemetry", "DeviceClass", "UserContext", "RoutingTarget", "RoutingState"}
REQUIRED_ROUTING_STATES = {"blocked", "dry_run", "routed", "fallback", "failed_closed"}
REQUIRED_TARGETS = {"local_1_7b", "local_4b", "central_server", "external_api", "blocked"}

def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    path = root / "schema" / "ip3_routing_contract.schema.json"
    if not path.exists():
        print("ROUTING_SCHEMA_GATE_FAIL missing schema/ip3_routing_contract.schema.json", file=sys.stderr)
        return 2
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    types = data.get("types", {})
    missing = REQUIRED_TYPES - set(types)
    if missing:
        errors.append(f"missing types={sorted(missing)}")
    states = set(types.get("RoutingState", {}).get("enum", []))
    if states != REQUIRED_ROUTING_STATES:
        errors.append(f"routing states mismatch={sorted(states)}")
    targets = set(types.get("RoutingTarget", {}).get("enum", []))
    if targets != REQUIRED_TARGETS:
        errors.append(f"routing targets mismatch={sorted(targets)}")
    if data.get("default_decision") != "blocked":
        errors.append("default_decision must be blocked")
    if data.get("release_claim_allowed_default") is not False:
        errors.append("release_claim_allowed_default must be false")
    if errors:
        for e in errors:
            print(f"ROUTING_SCHEMA_GATE_FAIL {e}", file=sys.stderr)
        return 2
    print("ROUTING_SCHEMA_GATE_OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
