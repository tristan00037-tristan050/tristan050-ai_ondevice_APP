from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from scripts.ai.final_verdict_v1 import (
    collect_stage_results,
    evaluate_final_verdict,
    write_final_report,
    run_final_verdict,
)

PASS_FILES = {
    "adapter_model.safetensors": b"x",
    "ai20_train_run_plan.json": '{"TRAIN_RUN_PLAN_' + 'OK":1}\nTRAIN_RUN_PLAN_' + 'OK=1',
    "adapter_config.json": '{"base_model_name_or_path":"Qwen/Qwen3-4B"}',
    "tmp/ai26_local_load_smoke_stdout.txt": 'LOCAL_LOAD_SMOKE_' + 'OK=' + '1',
    "tmp/ai26_output_format_smoke_stdout.txt": 'OUTPUT_FORMAT_SMOKE_' + 'OK=' + '1',
    "tmp/ai26_eval_6func_result.json": '{"EVAL_6FUNC_OK":"1"}',
    "tmp/ai27_compare_base_vs_ft_result.json": '{"BASE_VS_FT_OK":"1"}',
    "tmp/ai24_judge_hardcase_result.json": '{"JUDGE_HARDCASE_OK":"1"}',
    "tmp/phase_c_verification_result.json": '{"PHASE_C_VERIFICATION_OK":"1"}',
    "tmp/dual_model_verify_result.json": '{"DUAL_MODEL_VERIFY_OK":"1"}',
}


def make_base(tmp_path: Path) -> Path:
    for rel, content in PASS_FILES.items():
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            fp.write_bytes(content)
        else:
            fp.write_text(content, encoding="utf-8")
    return tmp_path


def get_report(tmp_path: Path):
    base = make_base(tmp_path)
    return evaluate_final_verdict(collect_stage_results(base), strict=True)


def test_collect_stage_results_returns_dict(tmp_path: Path):
    res = collect_stage_results(make_base(tmp_path))
    assert isinstance(res, dict)


def test_all_stages_present_in_result(tmp_path: Path):
    res = collect_stage_results(make_base(tmp_path))
    assert all(f"stage_{i:02d}" in res["stages"] for i in range(1, 11))


def test_verdict_pass_when_all_pass(tmp_path: Path):
    report = get_report(tmp_path)
    assert report["butler_final_verdict"] == "pass"


def test_verdict_fail_when_one_missing(tmp_path: Path):
    base = make_base(tmp_path)
    (base / "tmp/dual_model_verify_result.json").unlink()
    report = evaluate_final_verdict(collect_stage_results(base), strict=True)
    assert report["butler_final_verdict"] == "fail"


def test_verdict_fail_when_value_mismatch(tmp_path: Path):
    base = make_base(tmp_path)
    (base / "adapter_config.json").write_text('{"base_model_name_or_path":"OTHER"}', encoding="utf-8")
    report = evaluate_final_verdict(collect_stage_results(base), strict=True)
    assert report["butler_final_verdict"] == "fail"


def test_fail_code_recorded(tmp_path: Path):
    base = make_base(tmp_path)
    (base / "tmp/ai24_judge_hardcase_result.json").write_text('{"JUDGE_HARDCASE_OK":"0"}', encoding="utf-8")
    report = evaluate_final_verdict(collect_stage_results(base), strict=True)
    assert any(code.startswith("stage_08_") for code in report["fail_codes"])


def test_no_raw_text_in_report(tmp_path: Path):
    report = get_report(tmp_path)
    s = json.dumps(report, ensure_ascii=False).lower()
    assert '"prompt"' not in s
    assert '"output"' not in s


def test_schema_required_fields(tmp_path: Path):
    report = get_report(tmp_path)
    for key in ["schema_version", "stages", "pass_count", "butler_final_verdict"]:
        assert key in report


def test_generated_at_present(tmp_path: Path):
    report = get_report(tmp_path)
    assert "+00:00" in report["generated_at"]


def test_pass_count_equals_10(tmp_path: Path):
    report = get_report(tmp_path)
    assert report["pass_count"] == 10


def test_fail_count_zero_when_all_pass(tmp_path: Path):
    report = get_report(tmp_path)
    assert report["fail_count"] == 0


def test_stdout_contains_verdict(tmp_path: Path):
    base = make_base(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_final_verdict(base, tmp_path / "tmp/report.json", True, True)
    assert "BUTLER_FINAL_VERDICT=" in buf.getvalue()


def test_stdout_contains_pass_count(tmp_path: Path):
    base = make_base(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_final_verdict(base, tmp_path / "tmp/report.json", True, True)
    assert "FINAL_VERDICT_PASS_COUNT=" in buf.getvalue()


def test_json_out_written(tmp_path: Path):
    base = make_base(tmp_path)
    out = tmp_path / "tmp/report.json"
    run_final_verdict(base, out, True, True)
    assert out.exists()


def test_json_parseable(tmp_path: Path):
    report = get_report(tmp_path)
    out = tmp_path / "tmp/report.json"
    write_final_report(report, out)
    json.loads(out.read_text(encoding="utf-8"))


def test_dry_run_flag(tmp_path: Path):
    base = make_base(tmp_path)
    out = tmp_path / "tmp/report.json"
    run_final_verdict(base, out, True, True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["execution_mode"] == "dry_run"


def test_missing_file_graceful(tmp_path: Path):
    report = evaluate_final_verdict(collect_stage_results(tmp_path), strict=True)
    assert report["butler_final_verdict"] == "fail"
    assert report["fail_codes"]


def test_stage_evidence_not_raw(tmp_path: Path):
    report = get_report(tmp_path)
    for st in report["stages"].values():
        assert isinstance(st["evidence"], str)
        assert len(st["evidence"]) < 201


def test_verdict_field_only_pass_or_fail(tmp_path: Path):
    report = get_report(tmp_path)
    assert report["butler_final_verdict"] in {"pass", "fail"}


def test_schema_version_present(tmp_path: Path):
    report = get_report(tmp_path)
    assert report["schema_version"] == "2.0"


def test_strict_mode_requires_all_10(tmp_path: Path):
    base = make_base(tmp_path)
    (base / "tmp/ai26_local_load_smoke_stdout.txt").write_text('LOCAL_LOAD_SMOKE_OK=0', encoding="utf-8")
    report = evaluate_final_verdict(collect_stage_results(base), strict=True)
    assert report["butler_final_verdict"] == "fail"


def test_evidence_kind_structure_only_in_dryrun(tmp_path: Path):
    base = make_base(tmp_path)
    out = tmp_path / "tmp/report.json"
    run_final_verdict(base, out, True, True)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["evidence_kind"] == "structure_only"


def test_stage_source_relative_path(tmp_path: Path):
    report = get_report(tmp_path)
    assert not report["stages"]["stage_01"]["source"].startswith("/")


def test_multiple_conflict_records_fail_code(tmp_path: Path):
    base = make_base(tmp_path)
    extra = base / "tmp/another_dual_model_verify_result.json"
    extra.write_text('{"DUAL_MODEL_VERIFY_OK":"1"}', encoding="utf-8")
    report = evaluate_final_verdict(collect_stage_results(base), strict=True)
    assert "stage_10_multiple_conflict" in report["fail_codes"]
