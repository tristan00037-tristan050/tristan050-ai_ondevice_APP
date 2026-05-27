from pathlib import Path
from butler_pc_core.cards.box2.evaluator import REQUIRED_FIELDS, run_real_eval

class PassingDigestSafeChain:
    def generate_case(self, case):
        return {field: ("확인 필요" if field != "최종 문안" else "확인 필요 기준으로 최종 문안 작성") for field in REQUIRED_FIELDS}

def test_digest_safe_metric_proxy_passes_with_structured_outputs():
    root = Path(__file__).resolve().parents[3]
    payload = run_real_eval(PassingDigestSafeChain(), root / "data/box2_helper3_eval/eval_cases.jsonl")
    assert payload["sample_count"] == 20
    assert payload["rewrite_structure_accuracy"] == 1.0
    assert payload["required_field_coverage"] == 1.0
    assert payload["unsupported_fact_rate"] == 0.0
    assert payload["format_match_score"] == 1.0
    assert payload["semantic_preservation_score"] >= 0.85
    assert payload["status"] == "PASS_V2_FULL_METRIC"
    assert payload["mock_result"] is False
    assert payload["output_digest_only"] is True
    assert payload["raw_output_saved"] is False
