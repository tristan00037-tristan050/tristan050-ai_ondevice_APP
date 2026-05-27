import os
from pathlib import Path
import pytest
from butler_pc_core.cards.box2.evaluator import write_real_eval_evidence
from butler_pc_core.cards.box2.real_load_smoke import load_real_model_chain


def test_real_metric_v3_20_case_gate():
    if os.environ.get("BUTLER_BOX2_RUN_REAL_V3") != "1":
        pytest.skip("set BUTLER_BOX2_RUN_REAL_V3=1 on the MacBook runtime host")
    root = Path(__file__).resolve().parents[3]
    chain, load_evidence = load_real_model_chain()
    assert chain is not None, load_evidence
    payload = write_real_eval_evidence(chain, root / "data/box2_helper3_eval/eval_cases.jsonl", root / "evidence/box2_helper3/eval_metrics_real_v3.json")
    assert payload["sample_count"] >= 20
    assert payload["rewrite_structure_accuracy"] >= 0.85
    assert payload["required_field_coverage"] >= 0.90
    assert payload["unsupported_fact_rate"] <= 0.03
    assert payload["format_match_score"] >= 0.85
    assert payload["semantic_preservation_score"] >= 0.85
    assert payload["mock_result"] is False
    assert payload["status"] == "PASS_V2_FULL_METRIC"
