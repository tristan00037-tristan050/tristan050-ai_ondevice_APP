import json

from scripts.eval.eval_judge_v3 import run_full_eval


def test_judge_gate_basis_and_pass(tmp_path):
    eval_path = tmp_path / "eval.jsonl"
    eval_path.write_text("", encoding="utf-8")
    result = run_full_eval(
        None,
        None,
        [],
        model_version="test-model",
        dry_run=True,
        baseline_path=str(tmp_path / "baseline.json"),
        eval_set_path=str(eval_path),
        hardcase_file="data/eval/butler_hardcase_v1.jsonl",
        dataset_validation={"ok": True},
        report_path=str(tmp_path / "report.json"),
    )
    assert result.gate_basis == "fail_reasons_empty"
    assert result.passed is True
    assert result.hardcase["total_cases"] >= 50


def test_judge_report_contains_baseline_and_hardcase_fields(tmp_path):
    eval_path = tmp_path / "eval.jsonl"
    eval_path.write_text("", encoding="utf-8")
    report_path = tmp_path / "report.json"
    run_full_eval(
        None,
        None,
        [],
        model_version="test-model",
        dry_run=True,
        baseline_path=str(tmp_path / "baseline.json"),
        eval_set_path=str(eval_path),
        hardcase_file="data/eval/butler_hardcase_v1.jsonl",
        dataset_validation={"ok": True},
        report_path=str(report_path),
    )
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert "baseline_digest_before" in data["metadata"]
    assert "baseline_digest_after" in data["metadata"]
    assert "hardcase_digest" in data["metadata"]
    assert data["hardcase"]["passed_ratio"] == 1.0
