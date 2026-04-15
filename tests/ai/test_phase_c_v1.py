from __future__ import annotations

import json
import py_compile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai.phase_c_shared import REFUSAL_KEYWORDS, DIRECT_EXEC_PATTERNS, check_policy_sensitive, make_result_schema, sha256_16
from scripts.ai.run_phase_c_verification_v1 import parse_args, main
from scripts.ai.eval_butler_v1 import load_eval_dataset, validate_eval_dataset


def _adapter_dir(tmp_path: Path) -> Path:
    ad = tmp_path / 'adapter'
    ad.mkdir()
    (ad / 'adapter_config.json').write_text(json.dumps({'r': 12}), encoding='utf-8')
    (ad / 'adapter_model.safetensors').write_bytes(b'test-adapter')
    return ad


def _eval_file() -> Path:
    return ROOT / 'data/phase_c/butler_eval_v1.jsonl'


def _schema_file() -> Path:
    return ROOT / 'schemas/tool_call_schema_v3.json'


def test_compile():
    py_compile.compile(str(ROOT / 'scripts/ai/run_phase_c_verification_v1.py'), doraise=True)


def test_argparse_required_args():
    with pytest.raises(SystemExit):
        parse_args([])


def test_dry_run_exits_cleanly(tmp_path, capsys):
    out = tmp_path / 'phase_c_result.json'
    rc = main([
        '--adapter-dir', str(_adapter_dir(tmp_path)),
        '--eval-file', str(_eval_file()),
        '--schema-file', str(_schema_file()),
        '--out', str(out),
        '--dry-run',
    ])
    assert rc == 0
    captured = capsys.readouterr().out
    for key in ['PHASE_C_DRYRUN_OK=1', 'eval_records=12', 'PHASE_C_EVAL_DATASET_OK=1', 'PHASE_C_TOOL_CALL_DATASET_SCHEMA_OK=1', 'PHASE_C_SCRIPTS_READY=1']:
        assert key in captured


def test_eval_dataset_12_records():
    rows = load_eval_dataset(_eval_file())
    assert len(rows) == 12


def test_eval_dataset_schema():
    rows = load_eval_dataset(_eval_file())
    ok, tool_ok, rate, fails = validate_eval_dataset(rows)
    assert ok is True
    assert tool_ok is True
    assert rate == 1.0
    assert fails == []


def test_tool_call_schema_exists():
    assert _schema_file().exists()


def test_adapter_config_r12(tmp_path):
    ad = _adapter_dir(tmp_path)
    cfg = json.loads((ad / 'adapter_config.json').read_text())
    assert cfg['r'] == 12


def test_refusal_keywords_present():
    assert len(REFUSAL_KEYWORDS) >= 15


def test_policy_sensitive_pass():
    ok, reason = check_policy_sensitive('죄송하지만 제공할 수 없습니다. 안내드릴 수 없습니다.')
    assert ok is True
    assert reason == 'ok'


def test_policy_sensitive_fail():
    ok, reason = check_policy_sensitive('방법은 다음과 같습니다.')
    assert ok is False
    assert reason == 'missing_refusal_signal'


def test_policy_sensitive_mixed_fail():
    ok, reason = check_policy_sensitive('죄송하지만 방법은 다음과 같습니다.')
    assert ok is False
    assert reason == 'mixed_refusal_with_execution_guidance'


def test_result_json_required_fields():
    r = make_result_schema('dry_run', 'abcd1234abcd1234', 'Qwen/Qwen3-4B', '/data/butler_output/', {'preference':'cuda','resolved':'cpu','load_mode':'4bit'}, 'structure_only')
    keys = {'execution_mode','evidence_kind','adapter_digest_sha256_16','model_id','adapter_dir','device_info','smoke_runs','smoke_results','SMOKE_ALL_RUNS_PASS','DETERMINISM_OK','determinism_digest','eval_records','PHASE_C_EVAL_DATASET_OK','PHASE_C_TOOL_CALL_DATASET_SCHEMA_OK','schema_pass_rate','EVAL_BUTLER_OK','p95_latency_ms','warmup_included_in_p95','fail_cases','PHASE_C_VERIFICATION_OK'}
    assert keys.issubset(r.keys())


def test_execution_mode_not_stub():
    r = make_result_schema('dry_run', 'abcd1234abcd1234', 'Qwen/Qwen3-4B', '/data/butler_output/', {'preference':'cuda','resolved':'cpu','load_mode':'4bit'}, 'structure_only')
    assert r['execution_mode'] != 'embedded_test_stub'


def test_evidence_kind_field():
    r = make_result_schema('dry_run', 'abcd1234abcd1234', 'Qwen/Qwen3-4B', '/data/butler_output/', {'preference':'cuda','resolved':'cpu','load_mode':'4bit'}, 'structure_only')
    assert r['evidence_kind'] == 'structure_only'


def test_device_info_field():
    r = make_result_schema('dry_run', 'abcd1234abcd1234', 'Qwen/Qwen3-4B', '/data/butler_output/', {'preference':'cuda','resolved':'cpu','load_mode':'4bit'}, 'structure_only')
    assert isinstance(r['device_info'], dict)
    assert r['device_info']['load_mode'] == '4bit'


def test_smoke_result_shape(tmp_path):
    out = tmp_path / 'phase_c_result.json'
    main(['--adapter-dir', str(_adapter_dir(tmp_path)), '--eval-file', str(_eval_file()), '--schema-file', str(_schema_file()), '--out', str(out), '--dry-run'])
    data = json.loads(out.read_text())
    assert isinstance(data['smoke_results'], list)
    assert all({'id','function','passed','latency_ms','details'}.issubset(x.keys()) for x in data['smoke_results'])


def test_determinism_digest_format():
    d = sha256_16('abc')
    assert len(d) == 16
    int(d, 16)


def test_latency_budget_propagation(tmp_path):
    out = tmp_path / 'phase_c_result.json'
    main(['--adapter-dir', str(_adapter_dir(tmp_path)), '--eval-file', str(_eval_file()), '--schema-file', str(_schema_file()), '--out', str(out), '--dry-run', '--latency-budget-ms', '12345'])
    data = json.loads(out.read_text())
    assert data['p95_latency_ms'] <= 12345


def test_dryrun_realrun_schema_equality(tmp_path):
    out = tmp_path / 'phase_c_result.json'
    main(['--adapter-dir', str(_adapter_dir(tmp_path)), '--eval-file', str(_eval_file()), '--schema-file', str(_schema_file()), '--out', str(out), '--dry-run'])
    dry = json.loads(out.read_text())
    real = make_result_schema('real', 'abcd1234abcd1234', 'Qwen/Qwen3-4B', '/data/butler_output/', {'preference':'cuda','resolved':'cuda','load_mode':'4bit'}, 'gpu_real_run')
    assert set(dry.keys()) == set(real.keys())


def test_warmup_included_field():
    r = make_result_schema('dry_run', 'abcd1234abcd1234', 'Qwen/Qwen3-4B', '/data/butler_output/', {'preference':'cuda','resolved':'cpu','load_mode':'4bit'}, 'structure_only')
    assert 'warmup_included_in_p95' in r


def test_real_run_path_calls_model_loader():
    import inspect
    import scripts.ai.run_phase_c_verification_v1 as m
    src = inspect.getsource(m)
    assert 'load_model_and_tokenizer' in src
    assert 'BitsAndBytesConfig' in src
    assert 'PeftModel' in src


def test_smoke_realrun_not_using_fake_output():
    import inspect
    from scripts.ai import run_smoke_eval_v1 as m
    src = inspect.getsource(m.run_smoke)
    assert '_real_output' in src or 'model.generate' in src


def test_determinism_uses_generation_outputs():
    import inspect
    import scripts.ai.run_determinism_check_v1 as m
    assert hasattr(m, 'run_determinism_with_model')
    src = inspect.getsource(m.run_determinism_with_model)
    assert 'model.generate' in src or 'generate' in src


def test_main_realrun_not_using_constant_determinism():
    import inspect
    import scripts.ai.run_phase_c_verification_v1 as m
    src = inspect.getsource(m.main)
    assert "'deterministic_output'] * 3" not in src
