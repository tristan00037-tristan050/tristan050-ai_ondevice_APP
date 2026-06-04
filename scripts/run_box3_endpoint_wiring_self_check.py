from __future__ import annotations

from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
endpoint = ROOT / "butler_pc_core/cards/box3/endpoint_wiring.py"
route = ROOT / "butler_pc_core/sidecar/routes/box3_draft.py"

checks = {
    "endpoint_wiring_exists": endpoint.exists(),
    "route_candidate_exists": route.exists(),
    "approval_pre_gate_present": "evaluate_human_approval_sealed" in endpoint.read_text(encoding="utf-8"),
    "runner_injected_only_after_pre_gate": "runner_for_pipeline = runner if helper_guard_verdict.allowed else None" in endpoint.read_text(encoding="utf-8"),
    "legacy_route_preserved": "draft_from_existing" in route.read_text(encoding="utf-8"),
    "no_new_real_endpoint": "/v1/cards/3/draft/real" not in route.read_text(encoding="utf-8"),
    "old_contract_only_hardcode_removed": "run_box3_real_pipeline" not in route.read_text(encoding="utf-8"),
    "request_ui_flag_zero": not re.search(r"real_flag|request.*real.*true|approval.*payload", endpoint.read_text(encoding="utf-8"), re.I),
}
failed = [name for name, ok in checks.items() if not ok]
print(json.dumps({"checks": checks, "failed": failed}, ensure_ascii=False, indent=2))
if failed:
    sys.exit(1)
