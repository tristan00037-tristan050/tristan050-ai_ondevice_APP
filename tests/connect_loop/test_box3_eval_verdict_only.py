from pathlib import Path

from butler_pc_core.cards.box3.eval.evaluate_box3_verdict_only import evaluate_cases, load_eval_cases
from butler_pc_core.cards.box3.security import assert_no_raw_persistence, is_sha256_digest


def test_eval_40_cases_are_digest_only_and_cover_required_slices():
    path = Path(__file__).resolve().parents[2] / "butler_pc_core/cards/box3/eval/fixed_eval_cases.jsonl"
    cases = load_eval_cases(path)
    assert len(cases) == 40
    assert {case["document_type"] for case in cases} == {"보고서", "제안서", "공문", "요약"}
    assert {"easy", "medium", "hard"}.issubset({case["difficulty"] for case in cases})
    assert sum(1 for case in cases if case["has_table_or_figure"]) >= 8
    for case in cases:
        assert is_sha256_digest(case["source_digest"])
        assert is_sha256_digest(case["draft_request_digest"])
        assert is_sha256_digest(case["semantic_checklist_digest"])
        assert is_sha256_digest(case["format_marker_digest"])
        assert_no_raw_persistence(case)


def test_eval_summary_is_verdict_only_proxy_not_real_claim():
    path = Path(__file__).resolve().parents[2] / "butler_pc_core/cards/box3/eval/fixed_eval_cases.jsonl"
    result = evaluate_cases(load_eval_cases(path))
    summary = result["summary"]
    assert summary["sample_count"] == 40
    assert summary["metric_is_real_rewrite_measurement"] is False
    assert summary["metric_is_digest_safe_contract_proxy"] is True
    assert summary["mock_result"] is False
    assert summary["contract_only"] is True
    assert summary["status"] == "PARTIAL_CONTRACT_ONLY_ASSET_INVENTORY_PENDING"
    assert summary["pass_thresholds_met_by_proxy"] is True
    assert all("draft_text" not in verdict for verdict in result["verdicts"])

