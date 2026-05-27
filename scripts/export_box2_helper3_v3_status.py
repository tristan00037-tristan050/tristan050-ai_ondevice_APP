from __future__ import annotations
import json
from pathlib import Path
from butler_pc_core.cards.box2.evaluator import inspect_eval_set
from butler_pc_core.cards.box2.model_chain import build_model_chain_status
from butler_pc_core.cards.box2.runtime_loader import load_runtime
root = Path(__file__).resolve().parents[1]
payload = {"schema_version": "box2.helper3.status_export.v3", "runtime": load_runtime(), "model_chain": build_model_chain_status(allow_missing_assets=True).to_dict(), "eval_set": inspect_eval_set(root / "data/box2_helper3_eval/eval_cases.jsonl").to_dict()}
print(json.dumps(payload, ensure_ascii=False, indent=2))
