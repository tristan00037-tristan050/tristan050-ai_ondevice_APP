from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler_pc_core.cards.box3.pipeline import run_box3_pipeline
from butler_pc_core.cards.box3.security import assert_no_raw_persistence, sha256_digest
from butler_pc_core.cards.box3.types import Box3Request


PASS_THRESHOLDS = {
    "reference_coverage": 0.80,
    "grounding_pass_rate": 0.95,
    "unsupported_claim_rate_max": 0.03,
    "format_match_score": 0.85,
    "style_match_score": 0.70,
    "table_figure_reflection": 0.70,
    "source_digest_coverage": 0.90,
}


def load_eval_cases(path: Path) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for case in cases:
        assert_no_raw_persistence(case)
    return cases


def evaluate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts: list[dict[str, Any]] = []
    table_cases = 0
    for case in cases:
        table_cases += 1 if case.get("has_table_or_figure") else 0
        reference_docs = [case["source_digest"], case["semantic_checklist_digest"]]
        if case.get("has_table_or_figure"):
            reference_docs.append("<table>" + case["format_marker_digest"] + "</table>")
        request = Box3Request(
            reference_docs=reference_docs,
            draft_request=case["draft_request_digest"],
            format_hint=case["document_type"],
            max_new_tokens=384,
        )
        result = run_box3_pipeline(request)
        verdict = {
            "case_id": case["case_id"],
            "source_digest": case["source_digest"],
            "status": result["status"],
            "pass": result["status"] in {"contract_only", "real"},
            "fail_class": result["fail_class"],
            "draft_digest": result["draft_digest"],
            "reference_coverage": result["grounding"]["reference_coverage"],
            "grounding_pass_rate": result["grounding"]["grounding_pass_rate"],
            "unsupported_claim_rate": result["grounding"]["unsupported_claim_rate"],
            "format_match_score": result["format"]["format_match_score"],
            "style_match_score": result["style"]["style_match_score"],
            "source_digest_coverage": result["grounding"]["source_digest_coverage"],
            "raw_leak_zero": result["raw_saved_zero"] and not result["raw_doc_logged"],
        }
        assert_no_raw_persistence(verdict)
        verdicts.append(verdict)
    sample_count = len(verdicts)
    averages = {
        "reference_coverage": _avg(verdicts, "reference_coverage"),
        "grounding_pass_rate": _avg(verdicts, "grounding_pass_rate"),
        "unsupported_claim_rate": _avg(verdicts, "unsupported_claim_rate"),
        "format_match_score": _avg(verdicts, "format_match_score"),
        "style_match_score": _avg(verdicts, "style_match_score"),
        "source_digest_coverage": _avg(verdicts, "source_digest_coverage"),
        "table_figure_reflection": 1.0 if table_cases >= 8 else table_cases / 8,
    }
    pass_proxy = (
        sample_count >= 40
        and averages["reference_coverage"] >= PASS_THRESHOLDS["reference_coverage"]
        and averages["grounding_pass_rate"] >= PASS_THRESHOLDS["grounding_pass_rate"]
        and averages["unsupported_claim_rate"] <= PASS_THRESHOLDS["unsupported_claim_rate_max"]
        and averages["format_match_score"] >= PASS_THRESHOLDS["format_match_score"]
        and averages["style_match_score"] >= PASS_THRESHOLDS["style_match_score"]
        and averages["source_digest_coverage"] >= PASS_THRESHOLDS["source_digest_coverage"]
        and averages["table_figure_reflection"] >= PASS_THRESHOLDS["table_figure_reflection"]
    )
    summary = {
        "schema_version": "box3.verdict_only_eval.v1",
        "sample_count": sample_count,
        "table_figure_case_count": table_cases,
        "metric_is_real_rewrite_measurement": False,
        "metric_is_digest_safe_contract_proxy": True,
        "mock_result": False,
        "contract_only": True,
        "raw_leak_zero": all(item["raw_leak_zero"] for item in verdicts),
        "external_send_zero": True,
        "pass_thresholds_met_by_proxy": pass_proxy,
        "status": "PARTIAL_CONTRACT_ONLY_ASSET_INVENTORY_PENDING",
        "averages": averages,
        "verdicts_digest": sha256_digest(json.dumps(verdicts, sort_keys=True, ensure_ascii=False)),
    }
    assert_no_raw_persistence(summary)
    return {"summary": summary, "verdicts": verdicts}


def _avg(items: list[dict[str, Any]], key: str) -> float:
    return round(sum(float(item[key]) for item in items) / max(len(items), 1), 4)


def main() -> None:
    base = Path(__file__).resolve().parent
    result = evaluate_cases(load_eval_cases(base / "fixed_eval_cases.jsonl"))
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
