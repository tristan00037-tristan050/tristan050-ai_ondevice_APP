
from __future__ import annotations
import json
import py_compile
from pathlib import Path
import pytest
from scripts.ai.compare_base_vs_ft_v1 import parse_args, load_fixtures, sha256_16, main

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / 'scripts/ai/compare_base_vs_ft_v1.py'
ADAPTER_DIR = REPO_ROOT / 'tmp/test_adapter'
OUT_DIR = REPO_ROOT / 'tmp/test_out'


def _ensure_adapter_dir():
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    (ADAPTER_DIR / 'adapter_config.json').write_text(json.dumps({'r': 12, 'lora_alpha': 24}), encoding='utf-8')
    (ADAPTER_DIR / 'adapter_model.safetensors').write_bytes(b'butler-adapter-test')


def test_compile():
    py_compile.compile(str(SCRIPT), doraise=True)


def test_argparse_required_args():
    with pytest.raises(SystemExit):
        parse_args([])


def test_dry_run_exits_cleanly(capsys):
    _ensure_adapter_dir()
    rc = main(['--base-model-id','Qwen/Qwen3-4B','--adapter-dir',str(ADAPTER_DIR),'--output-dir',str(OUT_DIR),'--dry-run'])
    out = capsys.readouterr().out
    assert rc == 0
    assert 'DRYRUN_OK=1' in out


def test_fixture_load_18_prompts():
    prompts, summarize, retrieval = load_fixtures()
    assert len(prompts) == 18
    assert all({'id','func','user'} <= set(p.keys()) for p in prompts)


def test_fixture_func_distribution():
    prompts, _, _ = load_fixtures()
    counts = {}
    for p in prompts:
        counts[p['func']] = counts.get(p['func'], 0) + 1
    assert all(counts[f] == 3 for f in ['dialogue','summarize','rewrite','tool_call','policy_sensitive','retrieval_transform'])


def test_summarize_fixture_count():
    _, summarize, _ = load_fixtures()
    assert len(summarize) == 3


def test_retrieval_fixture_count():
    _, _, retrieval = load_fixtures()
    assert len(retrieval) == 3


def test_adapter_digest_format():
    _ensure_adapter_dir()
    d = sha256_16(ADAPTER_DIR / 'adapter_model.safetensors')
    assert len(d) == 16
    int(d, 16)


def test_result_json_required_fields():
    _ensure_adapter_dir()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    main(['--base-model-id','Qwen/Qwen3-4B','--adapter-dir',str(ADAPTER_DIR),'--output-dir',str(OUT_DIR),'--dry-run'])
    result = json.loads((OUT_DIR / 'compare_base_vs_ft_result.json').read_text())
    required = {'execution_mode','adapter_digest_sha256_16','base_model_id','adapter_dir','seed','max_new_tokens','temperature','thinking_mode','base_scores','ft_scores','overall_delta','statistical_confidence','score_details_summary','BASE_VS_FT_OK','fail_cases'}
    assert required <= set(result.keys())
    assert result['delta_scores'] is None or isinstance(result['delta_scores'], dict)


def test_execution_mode_not_stub():
    _ensure_adapter_dir()
    main(['--base-model-id','Qwen/Qwen3-4B','--adapter-dir',str(ADAPTER_DIR),'--output-dir',str(OUT_DIR),'--dry-run'])
    result = json.loads((OUT_DIR / 'compare_base_vs_ft_result.json').read_text())
    assert result['execution_mode'] != 'embedded_test_stub'


def test_fail_cases_format():
    _ensure_adapter_dir()
    main(['--base-model-id','Qwen/Qwen3-4B','--adapter-dir',str(ADAPTER_DIR),'--output-dir',str(OUT_DIR),'--dry-run'])
    result = json.loads((OUT_DIR / 'compare_base_vs_ft_result.json').read_text())
    assert isinstance(result['fail_cases'], list)

def test_dialogue_scoring_is_continuous():
    text = SCRIPT.read_text(encoding='utf-8')
    assert 'korean_score' in text and 'len_score' in text and 'context_score' in text


def test_report_jsonl_18_entries():
    p = OUT_DIR / 'compare_base_vs_ft_report.jsonl'
    if not p.exists():
        pytest.skip('real/dry-run report file absent')
    assert len([l for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]) == 18


def test_delta_score_all_positive():
    p = OUT_DIR / 'compare_base_vs_ft_result.json'
    if not p.exists():
        pytest.skip('result file absent')
    d = json.loads(p.read_text())
    if d['execution_mode'] != 'real':
        pytest.skip('real-run result absent')
    assert all(v > 0 for v in d['delta_scores'].values())


def test_overall_delta_threshold():
    p = OUT_DIR / 'compare_base_vs_ft_result.json'
    if not p.exists():
        pytest.skip('result file absent')
    d = json.loads(p.read_text())
    if d['execution_mode'] != 'real':
        pytest.skip('real-run result absent')
    assert d['overall_delta'] >= 0.30


def test_base_vs_ft_ok_flag():
    p = OUT_DIR / 'compare_base_vs_ft_result.json'
    if not p.exists():
        pytest.skip('result file absent')
    d = json.loads(p.read_text())
    if d['execution_mode'] != 'real':
        pytest.skip('real-run result absent')
    assert d['BASE_VS_FT_OK'] == 1
