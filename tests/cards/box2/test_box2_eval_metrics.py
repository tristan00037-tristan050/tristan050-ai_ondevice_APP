import json
from pathlib import Path

def test_box2_eval_metrics_real_v3_contract_fields_present():
    root = Path(__file__).resolve().parents[3]
    metrics = json.loads((root / "evidence/box2_helper3/eval_metrics_real_v3.json").read_text(encoding="utf-8"))
    assert metrics["sample_count"] == 20
    assert metrics["mock_result"] is False
    assert metrics["metric_is_digest_safe_proxy"] is True
    assert metrics["semantic_metric_kind"] == "digest_safe_checklist_proxy"

def test_box2_eval_metrics_status_is_honest_about_runtime_missing_in_sandbox():
    root = Path(__file__).resolve().parents[3]
    metrics = json.loads((root / "evidence/box2_helper3/eval_metrics_real_v3.json").read_text(encoding="utf-8"))
    assert metrics["status"] in {"PARTIAL_DONE_V3_RUNTIME_INSTALL_FAILED", "PARTIAL_DONE_V3_RUNTIME_IMPORT_ERROR", "PARTIAL_DONE_V3_STACKING_UNSUPPORTED", "PARTIAL_DONE_V3_EVAL_INSUFFICIENT", "PASS_V2_FULL_METRIC"}
