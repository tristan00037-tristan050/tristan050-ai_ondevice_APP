from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from butler_pc_core.cards.box2.evaluator import inspect_eval_set
from butler_pc_core.cards.box2.model_chain import build_model_chain_status

OUT = ROOT / "evidence" / "box2_helper3" / "local_preflight_report_v2.json"
EVAL = ROOT / "data" / "box2_helper3_eval" / "eval_cases.jsonl"

eval_set_report = inspect_eval_set(EVAL).to_dict()
eval_set_report["eval_set_path"] = "data/box2_helper3_eval/eval_cases.jsonl"

payload = {
    "schema_version": "box2.helper3.local_preflight_report.v2",
    "model_chain_status": build_model_chain_status(allow_missing_assets=True).to_dict(),
    "eval_set_report": eval_set_report,
    "claim_policy": {
        "macbook_real_run_claimed": False,
        "github_pr_created_claimed": False,
        "adapter_changed": False,
        "model_weight_changed": False,
        "retraining": False,
        "external_send": 0,
        "raw_persistence": 0,
    },
}

OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))
