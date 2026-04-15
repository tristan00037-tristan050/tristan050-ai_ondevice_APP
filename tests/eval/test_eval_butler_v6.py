from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'eval' / 'eval_butler_judge_v6.py'
FIXTURE = ROOT / 'scripts' / 'eval' / 'fixtures' / 'hardcase_v6.jsonl'
OUTDIR = ROOT / 'tmp'


def run_dry():
    adapter = OUTDIR / 'test_adapter'
    adapter.mkdir(parents=True, exist_ok=True)
    (adapter / 'adapter_config.json').write_text(json.dumps({'r':12,'lora_alpha':24}), encoding='utf-8')
    return subprocess.run([sys.executable, str(SCRIPT), '--model-id', 'Qwen/Qwen3-4B', '--adapter-dir', str(adapter), '--output-dir', str(OUTDIR), '--dry-run'], capture_output=True, text=True, check=False)


def test_compile():
    import py_compile
    py_compile.compile(str(SCRIPT), doraise=True)


def test_dryrun_stdout_keys():
    r=run_dry(); out=r.stdout
    key, val = 'DRYRUN_OK', '1'
    assert f'{key}={val}' in out
    assert 'hardcase_count=50' in out
    assert 'adversarial_refusal_count=15' in out
    assert 'adapter_r=12' in out
    key2, val2 = 'EVAL_BUTLER_DRYRUN_OK', '1'
    assert f'{key2}={val2}' in out


def test_dataset_size_50():
    assert len(FIXTURE.read_text(encoding='utf-8').splitlines()) == 50


def test_adversarial_15():
    rows=[json.loads(x) for x in FIXTURE.read_text(encoding='utf-8').splitlines() if x.strip()]
    assert sum(1 for r in rows if r['category']=='adversarial_refusal') == 15


def test_must_refuse_15():
    rows=[json.loads(x) for x in FIXTURE.read_text(encoding='utf-8').splitlines() if x.strip()]
    assert sum(1 for r in rows if r.get('must_refuse')) == 15


def test_fixture_prompt_is_korean_not_placeholder():
    first=json.loads(FIXTURE.read_text(encoding='utf-8').splitlines()[0])
    assert 'prompt' in first and 'prompt 1' not in first['prompt']
    assert any('가' <= c <= '힣' for c in first['prompt'])


def test_result_schema_exists_after_dryrun():
    run_dry()
    p=OUTDIR/'eval_butler_result.json'
    d=json.loads(p.read_text())
    for k in ['execution_mode','adapter_digest_sha256_16','model_id','adapter_dir','hardcase_total','hardcase_passed','hardcase_passed_ratio','adversarial_refused','adversarial_total','category_results','fail_cases','EVAL_BUTLER_REAL_RUN_OK']:
        assert k in d


def test_execution_mode_dry_run():
    run_dry()
    d=json.loads((OUTDIR/'eval_butler_result.json').read_text())
    assert d['execution_mode'] == 'dry_run'


def test_schema_equality_dry_real():
    from scripts.eval.eval_judge_v3 import make_result_schema
    a=set(make_result_schema('dry_run','0'*16,'Qwen/Qwen3-4B','/data/butler_output/').keys())
    b=set(make_result_schema('real','0'*16,'Qwen/Qwen3-4B','/data/butler_output/').keys())
    assert a == b


def test_weighted_scoring_pass_case():
    from scripts.eval.eval_judge_v3 import score_case
    case={'category':'confusing_context','expected_keywords':['해지','해제','차이']}
    passed, details = score_case(case, '계약 해지와 해제의 차이를 설명합니다.')
    assert passed is True
    assert details['case_score'] >= 0.6


def test_weighted_scoring_rule_only_fails():
    from scripts.eval.eval_judge_v3 import score_case
    case={'category':'confusing_context','expected_keywords':['해지','해제','차이']}
    passed, details = score_case(case, '짧음')
    assert passed is False


def test_adversarial_refusal_passes_on_refusal():
    from scripts.eval.eval_judge_v3 import score_case
    case={'category':'adversarial_refusal','must_refuse':True,'expected_keywords':[]}
    passed, details = score_case(case, '죄송하지만 제공할 수 없습니다.')
    assert passed is True


def test_hardcase_only_flag_parses():
    from scripts.eval.eval_butler_judge_v6 import parse_args
    args=parse_args(['--model-id','Qwen/Qwen3-4B','--adapter-dir','/data/butler_output/','--output-dir','tmp','--hardcase-only'])
    assert args.hardcase_only is True


def test_quantization_config_contract_text():
    txt=(ROOT/'scripts'/'eval'/'eval_runner_v3.py').read_text(encoding='utf-8')
    assert 'load_in_4bit=True' in txt
    assert "bnb_4bit_quant_type='nf4'" in txt or '"nf4"' in txt
    assert 'torch.bfloat16' in txt


def test_fixture_categories_present():
    rows=[json.loads(x) for x in FIXTURE.read_text(encoding='utf-8').splitlines() if x.strip()]
    cats={r['category'] for r in rows}
    assert cats == {'confusing_context','boundary_case','adversarial_refusal','domain_crossing','negation_trap'}


def test_fail_cases_list_type():
    run_dry()
    d=json.loads((OUTDIR/'eval_butler_result.json').read_text())
    assert isinstance(d['fail_cases'], list)


def test_hardcase_counts_in_result():
    run_dry()
    d=json.loads((OUTDIR/'eval_butler_result.json').read_text())
    assert d['hardcase_total']==50
    assert d['adversarial_total']==15


def test_realrun_path_contains_load_real_model_and_score_case():
    text = SCRIPT.read_text(encoding='utf-8')
    assert 'load_real_model' in text
    assert 'score_case(case, output)' in text


def test_realrun_result_file_schema_when_called_skips_without_runtime():
    pytest.skip('GPU real-run은 운영팀 범위')


def test_result_json_fields_nonmissing():
    run_dry()
    d=json.loads((OUTDIR/'eval_butler_result.json').read_text())
    assert len(d.keys()) == 12


def test_fixture_lines_json_parseable():
    for line in FIXTURE.read_text(encoding='utf-8').splitlines():
        assert isinstance(json.loads(line), dict)


def test_cli_requires_args():
    r=subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False)
    assert r.returncode != 0


def test_dryrun_creates_result_file():
    run_dry()
    assert (OUTDIR/'eval_butler_result.json').exists()


def test_bundle_check_placeholder():
    assert SCRIPT.exists()


def test_model_id_arg_parsing():
    from scripts.eval.eval_butler_judge_v6 import parse_args
    args=parse_args(['--model-id','Qwen/Qwen3-4B','--adapter-dir','/data/butler_output/','--output-dir','tmp'])
    assert args.model_id == 'Qwen/Qwen3-4B'


def test_adapter_dir_arg_parsing():
    from scripts.eval.eval_butler_judge_v6 import parse_args
    args=parse_args(['--model-id','Qwen/Qwen3-4B','--adapter-dir','/data/butler_output/','--output-dir','tmp'])
    assert args.adapter_dir == '/data/butler_output/'


def test_output_dir_arg_parsing():
    from scripts.eval.eval_butler_judge_v6 import parse_args
    args=parse_args(['--model-id','Qwen/Qwen3-4B','--adapter-dir','/data/butler_output/','--output-dir','tmp'])
    assert args.output_dir == 'tmp'


def test_realrun_ratio_threshold_skip():
    pytest.skip('GPU real-run 결과 기반 검증은 운영팀 범위')


def test_realrun_ok_flag_skip():
    pytest.skip('GPU real-run 결과 기반 검증은 운영팀 범위')
