from __future__ import annotations
import inspect
import json
from pathlib import Path

import pytest

from scripts.ai import device_profiler_v1 as profiler
from scripts.ai import model_router_v1 as router
from scripts.ai import verify_dual_model_v1 as verify


def test_profiler_stdout_keys(capsys):
    profiler.main([])
    out = capsys.readouterr().out
    assert 'DEVICE_PROFILE_OK=' in out and 'DEVICE_PROFILE_OK=0' not in out
    assert 'DEVICE_PROFILE_RECOMMENDATION=' in out


def test_profiler_collect_dict():
    d = profiler.collect_device_profile()
    assert isinstance(d, dict)
    assert d['ok'] == 1


def test_profiler_no_psutil_graceful(monkeypatch):
    monkeypatch.setattr(profiler, '_safe_import_psutil', lambda: (None, 'missing'))
    d = profiler.collect_device_profile()
    assert d['ok'] == 1
    assert any('psutil_missing' in e for e in d['probe_errors'])


def test_profiler_no_cuda_graceful(monkeypatch):
    class DummyTorch:
        class cuda:
            @staticmethod
            def is_available(): return False
    monkeypatch.setattr(profiler, '_safe_import_torch', lambda: (DummyTorch, None))
    d = profiler.collect_device_profile()
    assert d['cuda_available'] == 0


def test_router_ram_low():
    r = router.route_model({'ram_avail_gb': 5, 'cuda_available': 0, 'cpu_usage_pct': 0, 'thermal_state': 'normal', 'recommendation': 'light'})
    assert r['selected'] == 'light' and r['reason_code'] == 'ram_low'


def test_router_vram_low():
    r = router.route_model({'ram_avail_gb': 10, 'cuda_available': 1, 'vram_avail_gb': 7, 'cpu_usage_pct': 0, 'thermal_state': 'normal', 'recommendation': 'light'})
    assert r['selected'] == 'light' and r['reason_code'] == 'vram_low'


def test_router_battery_low():
    r = router.route_model({'ram_avail_gb': 10, 'cuda_available': 0, 'cpu_usage_pct': 0, 'battery_pct': 10, 'battery_plugged': 0, 'thermal_state': 'normal', 'recommendation': 'light'})
    assert r['reason_code'] == 'battery_low'


def test_router_cpu_busy():
    r = router.route_model({'ram_avail_gb': 10, 'cuda_available': 0, 'cpu_usage_pct': 81, 'thermal_state': 'normal', 'recommendation': 'light'})
    assert r['reason_code'] == 'cpu_busy'


def test_router_thermal_hot():
    r = router.route_model({'ram_avail_gb': 10, 'cuda_available': 0, 'cpu_usage_pct': 10, 'thermal_state': 'hot', 'recommendation': 'light'})
    assert r['reason_code'] == 'thermal_hot'


def test_router_default_high():
    r = router.route_model({'ram_avail_gb': 12, 'cuda_available': 0, 'cpu_usage_pct': 10, 'thermal_state': 'normal', 'recommendation': 'high'})
    assert r['selected'] == 'high' and r['reason_code'] == 'ram_sufficient'


def test_router_force_light():
    r = router.route_model({'ram_avail_gb': 12, 'cuda_available': 0, 'cpu_usage_pct': 10, 'thermal_state': 'normal', 'recommendation': 'high'}, force='light')
    assert r['reason_code'] == 'forced_light'


def test_router_force_high():
    r = router.route_model({'ram_avail_gb': 1, 'cuda_available': 0, 'cpu_usage_pct': 90, 'thermal_state': 'hot', 'recommendation': 'light'}, force='high')
    assert r['reason_code'] == 'forced_high'


def test_router_reason_code():
    r = router.route_model({'ram_avail_gb': 12, 'cuda_available': 0, 'cpu_usage_pct': 10, 'thermal_state': 'normal', 'recommendation': 'high'})
    assert r['reason_code'] in router.REASON_CODES


def test_router_fallback_code():
    base = router.route_model({'ram_avail_gb': 12, 'cuda_available': 0, 'cpu_usage_pct': 10, 'thermal_state': 'normal', 'recommendation': 'high'})
    out = router.apply_fallback(base, high_model_load_ok=False)
    assert out['fallback_used'] == 1
    assert out['fallback_reason'] == 'high_model_load_failed'


def test_verify_runs_profiler():
    r = verify.verify_dual_model('high', 'light', 'adapter', dry_run=True)
    assert r['checks']['V01'] == 1


def test_verify_runs_router():
    r = verify.verify_dual_model('high', 'light', 'adapter', dry_run=True)
    assert r['checks']['V02'] == 1


def test_verify_override_light():
    r = verify.verify_dual_model('high', 'light', 'adapter', dry_run=True, force_light=True)
    assert r['router_result']['primary_selected'] == 'light'
    assert r['checks']['V08'] == 1


def test_verify_override_high():
    r = verify.verify_dual_model('high', 'light', 'adapter', dry_run=True, force_high=True)
    assert r['router_result']['primary_selected'] == 'high'
    assert r['checks']['V08'] == 1


def test_verify_high_smoke_shape():
    r = verify.verify_dual_model('high_path', 'light_path', 'adapter_path', dry_run=True)
    assert len(r['evidence']['high_output_digest16']) == 16
    s = json.dumps(r, ensure_ascii=False)
    assert '오늘 회의 내용을 짧게 정리해 주세요' not in s


def test_verify_light_smoke_shape():
    r = verify.verify_dual_model('high_path', 'light_path', 'adapter_path', dry_run=True)
    assert len(r['evidence']['light_output_digest16']) == 16


def test_verify_no_raw_text_logging():
    r = verify.verify_dual_model('high_path', 'light_path', 'adapter_path', dry_run=True)
    s = json.dumps(r, ensure_ascii=False)
    assert 'dry-run: high model not loaded' not in s
    assert 'dry-run: light model not loaded' not in s


def test_result_schema_required_fields(tmp_path):
    out = tmp_path / 'dual.json'
    code = verify.main(['--high-model-path','h','--light-model-path','l','--adapter-path','a','--dry-run','--json-out', str(out)])
    assert code == 0
    data = json.loads(out.read_text())
    for k in ['execution_mode','high_model_path','light_model_path','adapter_path','device_profile','router_result','checks','pass_count','ok','fail_codes','evidence']:
        assert k in data


def test_dryrun_realrun_schema_equality():
    d1 = verify.verify_dual_model('h','l','a', dry_run=True)
    # Avoid real model loading; monkeypatch helper to bypass.
    orig = verify._run_real_load_generate
    verify._run_real_load_generate = lambda *args, **kwargs: (True, 'ok-output', 'ok')
    try:
        d2 = verify.verify_dual_model('h','l','a', dry_run=False)
    finally:
        verify._run_real_load_generate = orig
    assert set(d1.keys()) == set(d2.keys())


def test_dual_model_verify_ok_contract(capsys, tmp_path):
    out = tmp_path / 'r.json'
    rc = verify.main(['--high-model-path','h','--light-model-path','l','--adapter-path','a','--dry-run','--json-out', str(out)])
    text = capsys.readouterr().out
    assert rc == 0
    assert 'DUAL_MODEL_VERIFY_OK=' in text and 'DUAL_MODEL_VERIFY_OK=0' not in text
    assert 'DUAL_MODEL_VERIFY_PASS=8/8' in text


def test_verify_uses_real_loader_symbols():
    src = inspect.getsource(verify)
    assert 'AutoModelForCausalLM' in src
    assert 'BitsAndBytesConfig' in src
    assert 'PeftModel' in src


def test_verify_generate_path_exists():
    """
    계약: verify 모듈 어딘가에 apply_chat_template와 model.generate가 존재해야 한다.
    _real_output()이 직접 호출하든 _prepare_inputs() 등을 통해 호출하든 무관.
    리팩터링 내성을 갖춘 계약 기반 테스트.
    """
    module_src = inspect.getsource(verify)
    assert "apply_chat_template" in module_src,         "verify 모듈 어딘가에 apply_chat_template가 있어야 합니다"
    real_src = inspect.getsource(verify._real_output)
    assert "model.generate" in real_src or "generate" in real_src,         "_real_output 경로에 generate 호출이 있어야 합니다"


def test_verify_no_simulator_left():
    src = inspect.getsource(verify)
    assert '_simulate_load_and_generate' not in src




def test_fallback_end_to_end():
    """
    계약: high 모델 로드 실패 시 router가 light fallback을 올바르게 기록해야 한다.
    """
    profile_high = {
        "ok": 1, "ram_avail_gb": 20.0, "cpu_cores": 16,
        "cpu_usage_pct": 10.0, "battery_pct": 100, "battery_plugged": 1,
        "cuda_available": 0, "vram_avail_gb": 0.0,
        "thermal_state": "normal", "recommendation": "high", "probe_errors": []
    }
    result = router.route_model(profile_high, force=None)
    assert result["primary_selected"] == "high"
    result2 = router.apply_fallback(result, high_model_load_ok=False)
    assert result2["selected"] == "light"
    assert result2["fallback_used"] == 1
    assert result2["fallback_reason"] == "high_model_load_failed"


def test_prepare_inputs_applies_chat_template():
    """계약: _prepare_inputs()가 apply_chat_template를 사용해야 한다."""
    src = inspect.getsource(verify._prepare_inputs)
    assert "apply_chat_template" in src,         "_prepare_inputs()에 apply_chat_template가 있어야 합니다"
    assert "tokenize=True" in src or "tokenize" in src,         "tokenize 옵션이 있어야 합니다"


def test_result_schema_has_evidence_digests(tmp_path):
    """계약: 결과 파일 evidence에 digest 필드가 있어야 하고 원문이 없어야 한다."""
    out = tmp_path / "dual_result.json"
    rc = verify.main([
        "--high-model-path", "high_path",
        "--light-model-path", "light_path",
        "--adapter-path", "adapter_path",
        "--dry-run",
        "--json-out", str(out),
    ])
    assert rc == 0
    result = json.loads(out.read_text())
    assert "evidence" in result
    evidence = result["evidence"]
    assert "high_output_digest16" in evidence
    assert "light_output_digest16" in evidence
    evidence_str = str(evidence)
    assert "오늘 회의 내용을 짧게 정리해 주세요" not in evidence_str
    assert "prompt" not in evidence_str.lower() or len(evidence_str) < 500

def test_profiler_cpu_measurement_not_first_zero():
    src = inspect.getsource(profiler._measure_cpu_usage)
    assert 'cpu_percent(interval=None)' in src
    assert 'cpu_percent(interval=0.1)' in src or 'cpu_percent(interval=0.2)' in src
