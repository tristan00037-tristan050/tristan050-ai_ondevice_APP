from scripts.eval.eval_regression_v3 import persist_baseline, run_regression_eval


def test_regression_create_pending(tmp_path):
    path = tmp_path / "baseline.json"
    result = run_regression_eval({"bleu4": 0.2}, baseline_path=path, dry_run=False)
    assert result.baseline_exists is False
    assert result.baseline_action == "create_pending_on_pass"


def test_regression_detect_drop(tmp_path):
    path = tmp_path / "baseline.json"
    persist_baseline({"bleu4": 1.0, "avg_latency_sec": 1.0}, baseline_path=path, model_version="v1", report_path="tmp/x.json")
    result = run_regression_eval({"bleu4": 0.8, "avg_latency_sec": 1.2}, baseline_path=path, dry_run=False)
    assert result.passed is False
    assert any(reason.startswith("EVAL_FAIL_REGRESSION_BLEU4") for reason in result.fail_reasons)
