import json
from pathlib import Path


def test_box2_eval_metrics_contract_only_but_not_missing():
    root = Path(__file__).resolve().parents[3]
    metrics = json.loads((root / "evidence/box2_helper3/eval_metrics.json").read_text(encoding="utf-8"))
    assert metrics["eval_set_path"] == "data/box2_helper3_eval/eval_cases.jsonl"
    assert metrics["sample_count"] == 20
    assert metrics["mock_result"] is False
    assert metrics["contract_only"] is True


def test_box2_eval_metrics_status_is_honest_about_lora_pending():
    root = Path(__file__).resolve().parents[3]
    metrics = json.loads((root / "evidence/box2_helper3/eval_metrics.json").read_text(encoding="utf-8"))
    assert metrics["status"] == "PARTIAL_DONE_V2_LORA_SHA_SCOPE_PENDING"
