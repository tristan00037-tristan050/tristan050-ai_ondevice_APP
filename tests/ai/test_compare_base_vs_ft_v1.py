
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/ai/compare_base_vs_ft_v1.py'
ADAPTER = ROOT / 'tmp/test_adapter'
OUTDIR = ROOT / 'tmp/test_out'


def run_dry():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(SCRIPT), '--base-model-id', 'Qwen/Qwen3-4B', '--adapter-dir', str(ADAPTER), '--output-dir', str(OUTDIR), '--dry-run']
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def test_compile():
    import py_compile
    py_compile.compile(str(SCRIPT), doraise=True)


def test_argparse_required_args():
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode != 0


def test_dry_run_exits_cleanly():
    r = run_dry()
    assert r.returncode == 0
    out = r.stdout
    key, val = 'DRYRUN_OK', '1'
    assert f'{key}={val}' in out


def test_fixture_load_18_prompts():
    lines = (ROOT/'scripts/ai/fixtures/compare_prompts_v1.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 18
    row = json.loads(lines[0])
    assert {'id','func','user'} <= set(row)


def test_fixture_func_distribution():
    rows = [json.loads(l) for l in (ROOT/'scripts/ai/fixtures/compare_prompts_v1.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    counts = {}
    for r in rows:
        counts[r['func']] = counts.get(r['func'], 0) + 1
    assert all(counts.get(f, 0) == 3 for f in ['dialogue','summarize','rewrite','tool_call','policy_sensitive','retrieval_transform'])


def test_summarize_fixture_count():
    data = json.loads((ROOT/'scripts/ai/fixtures/summarize_texts_v1.json').read_text(encoding='utf-8'))
    assert len(data) == 3


def test_retrieval_fixture_count():
    data = json.loads((ROOT/'scripts/ai/fixtures/retrieval_texts_v1.json').read_text(encoding='utf-8'))
    assert len(data) == 3


def test_adapter_digest_format():
    r = run_dry()
    assert r.returncode == 0
    result = json.loads((OUTDIR/'compare_base_vs_ft_result.json').read_text(encoding='utf-8'))
    digest = result['adapter_digest_sha256_16']
    assert len(digest) == 16
    int(digest, 16)


def test_result_json_required_fields():
    run_dry()
    result = json.loads((OUTDIR/'compare_base_vs_ft_result.json').read_text(encoding='utf-8'))
    required = ['execution_mode','adapter_digest_sha256_16','base_model_id','adapter_dir','seed','max_new_tokens','temperature','thinking_mode','base_scores','ft_scores','delta_scores','overall_delta','statistical_confidence','score_details_summary','BASE_VS_FT_OK','fail_cases']
    for k in required:
        assert k in result
    assert result['delta_scores'] is None or isinstance(result['delta_scores'], dict)


def test_execution_mode_not_stub():
    run_dry()
    result = json.loads((OUTDIR/'compare_base_vs_ft_result.json').read_text(encoding='utf-8'))
    assert result['execution_mode'] != 'embedded_test_stub'


def test_fail_cases_format():
    run_dry()
    result = json.loads((OUTDIR/'compare_base_vs_ft_result.json').read_text(encoding='utf-8'))
    assert isinstance(result['fail_cases'], list)


def test_dialogue_scoring_continuous_present():
    text = SCRIPT.read_text(encoding='utf-8')
    assert 'korean_score' in text and 'len_score' in text and 'context_score' in text


def test_report_jsonl_18_entries():
    p = OUTDIR/'compare_base_vs_ft_report.jsonl'
    if not p.exists():
        pytest.skip('dry-run not executed yet')
    lines = p.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 18


def test_delta_score_all_positive():
    pytest.skip('real-run 결과 파일 기반 테스트')


def test_overall_delta_threshold():
    pytest.skip('real-run 결과 파일 기반 테스트')


def test_base_vs_ft_ok_flag():
    pytest.skip('real-run 결과 파일 기반 테스트')
