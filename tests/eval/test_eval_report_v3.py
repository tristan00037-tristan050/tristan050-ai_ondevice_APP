import json

from scripts.eval.eval_report_v3 import generate_report


def test_generate_report_writes_markdown(tmp_path):
    report_json = tmp_path / "report.json"
    summary_md = tmp_path / "summary.md"
    report_json.write_text(
        json.dumps(
            {
                "passed": True,
                "gate_basis": "fail_reasons_empty",
                "overall_score": 0.99,
                "fail_reasons": [],
                "basic": {"bleu4": 0.99, "rouge_l": 0.99, "avg_latency_sec": 1.0, "avg_response_length": 120.0},
                "domain": {
                    "scores": {"legal": 0.99, "finance": 0.99, "medical": 0.99, "admin": 0.99, "general": 0.99},
                    "sample_counts": {"legal": 10, "finance": 10, "medical": 10, "admin": 10, "general": 10},
                    "judge_extension": {
                        "rule_judge": {"enabled": True, "source": "rule_v1"},
                        "llm_as_judge": {"enabled": False},
                        "human_spot_check": {"enabled": False},
                    },
                },
                "safety": {"policy_refusal_accuracy": 0.99, "hallucination_ratio": 0.01},
                "hardcase": {
                    "total_cases": 50,
                    "passed_cases": 50,
                    "adversarial_total": 15,
                    "adversarial_refused": 15,
                    "passed_ratio": 1.0,
                    "refusal_ratio": 1.0,
                    "bucket_counts": {"confusing_context": 10},
                    "results": [],
                    "passed": True,
                    "fail_reasons": [],
                },
                "regression": {"baseline_exists": False, "regressions": [], "comparisons": {}, "baseline_action": "dry_run_no_write"},
                "metadata": {
                    "git_sha": "unknown",
                    "config_digest": "abc",
                    "eval_set_digest": "def",
                    "hardcase_digest": "ghi",
                    "baseline_digest_before": None,
                    "baseline_digest_after": None,
                    "baseline_updated": False,
                    "elapsed_seconds": 1.0,
                    "environment": {"python": "3.11", "platform": "linux"},
                    "dataset_validation": {"total_rows": 150, "per_domain": {"legal": 30}},
                    "hardcase_counts": {"total": 50, "must_refuse": 15, "bucket_counts": {"confusing_context": 10}},
                },
                "model_version": "butler_model_small_v1",
                "eval_timestamp": "2026-03-29T00:00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    markdown = generate_report(str(report_json), str(summary_md))
    assert summary_md.exists()
    assert "hard-case / adversarial" in markdown
    assert "judge 확장 상태" in markdown
