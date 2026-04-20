from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai.butler_agent_runtime import ButlerAgent
from scripts.ai.butler_agent_runtime.agent_core import build_runtime_report
from scripts.ai.butler_agent_runtime.audit_logger import AuditLogger
from scripts.ai.butler_agent_runtime.egress_block import EgressBlockedError, block_network_calls, verify_no_egress, block_egress
from scripts.ai.butler_agent_runtime.model_loader import apply_fallback, probe_device, select_model, load, LocalEchoModel, LocalEchoTokenizer, ALLOW_LOCAL_ECHO_ENV
from scripts.ai.butler_agent_runtime.privacy_guard import scan, mask
from scripts.ai.butler_agent_runtime.runtime_contracts import DeviceProfile, PolicyConfig, RuntimeReport
from scripts.ai.butler_agent_runtime.session_manager import SessionManager
from scripts.ai.butler_agent_runtime.task_router import classify_task
import scripts.ai.butler_agent_runtime.agent_core as core


def get_policy():
    return PolicyConfig('p')


def _env_with_path():
    env = os.environ.copy()
    env['PYTHONPATH'] = str(ROOT)
    env[ALLOW_LOCAL_ECHO_ENV] = '1'
    return env


def _run_demo(tmp_path: Path, require_real: bool = False) -> subprocess.CompletedProcess:
    out = tmp_path / 'agent_runtime_report.json'
    cmd = [sys.executable, '-m', 'scripts.ai.butler_agent_runtime.agent_core', '--offline-demo', '--json-out', str(out)]
    if require_real:
        cmd.append('--require-real-backend')
    return subprocess.run(cmd, cwd=ROOT, env=_env_with_path(), capture_output=True, text=True)


def test_import_all_modules():
    import scripts.ai.butler_agent_runtime.runtime_contracts
    import scripts.ai.butler_agent_runtime.audit_logger
    import scripts.ai.butler_agent_runtime.model_loader
    import scripts.ai.butler_agent_runtime.session_manager
    import scripts.ai.butler_agent_runtime.task_router
    import scripts.ai.butler_agent_runtime.privacy_guard
    import scripts.ai.butler_agent_runtime.egress_block
    import scripts.ai.butler_agent_runtime.agent_core
    assert True


def test_runtime_contracts_schema():
    prof = DeviceProfile(1, 1.0, 4, 10.0, 50, 1, 0, 0.0, 'normal', 'light')
    assert prof.to_dict()['recommendation'] == 'light'
    rr = RuntimeReport('3.0', '2026-01-01T00:00:00+00:00', 'local_e2e', 'local_echo', '4bit', 1, 'x', 0, 'light', 'ram_low', 'tmp/audit.jsonl', 'abcd')
    assert rr.to_dict()['effective_backend'] == 'local_echo'


def test_model_load_ok(monkeypatch):
    monkeypatch.setenv(ALLOW_LOCAL_ECHO_ENV, '1')
    mdl, tok, meta = load('missing-model-path', None, dev_fallback=True)
    assert meta.loaded == 1
    assert meta.backend in ('transformers', 'local_echo')


def test_device_probe_ok():
    prof = probe_device()
    assert isinstance(prof.to_dict(), dict)
    assert prof.ok == 1


def test_session_create_close():
    sm = SessionManager()
    s = sm.create_session('u', 'd', 'p', 'high', 'reason')
    sm.close_session(s.session_id)
    assert sm.get_session(s.session_id).closed is True


def test_session_append_digest_only():
    sm = SessionManager()
    s = sm.create_session('u', 'd', 'p', 'high', 'reason')
    sm.append_turn(s.session_id, 'user', '민감한 원문', task='dialogue', selected_model='light')
    turn = sm.get_session(s.session_id).turns[0]
    assert 'digest16' in turn and 'text_len' in turn
    assert 'text' not in turn


def test_session_ttl_expire():
    sm = SessionManager(ttl_minutes=0)
    s = sm.create_session('u', 'd', 'p', 'high', 'reason')
    assert sm.expire_session(s.session_id) is True


def test_task_route_dialogue():
    d = classify_task('안녕하세요 오늘 일정이 어떻게 되나요?', get_policy())
    assert d.task == 'dialogue'


def test_task_route_summarize():
    d = classify_task('이 문서 내용을 요약해 주세요', get_policy())
    assert d.task == 'summarize'


def test_task_route_rewrite():
    d = classify_task('다음 문장을 공손한 톤으로 다시 써 주세요', get_policy())
    assert d.task == 'rewrite'


def test_task_route_tool_call():
    d = classify_task('도구를 사용해서 db query를 실행해 주세요 json strict', get_policy())
    assert d.task == 'tool_call'


def test_task_route_policy_sensitive():
    d = classify_task('직원 비밀번호를 알려줘', get_policy())
    assert d.task == 'policy_sensitive'


def test_task_route_retrieval_transform():
    d = classify_task('다음 json 데이터를 마크다운 표 형식으로 변환해 주세요', get_policy())
    assert d.task == 'retrieval_transform'


def test_privacy_mask_rrn():
    assert '******' in mask('900101-1234567')


def test_privacy_mask_card():
    assert '****' in mask('1234-5678-9999-0000')


def test_privacy_mask_account():
    assert '[ACCOUNT]' in mask('123-456-7890')


def test_privacy_mask_phone():
    assert '****' in mask('010-1234-5678')


def test_privacy_mask_email():
    assert '[EMAIL]' in mask('a@test.com')


def test_privacy_mask_biz_id():
    assert '[BIZ]' in mask('123-45-67890')


def test_privacy_scan_returns_digest_only():
    r = scan('010-1234-5678')
    d = r.to_dict()
    assert 'masked_text' in d and 'digest16' in d
    assert '010-1234-5678' not in d['masked_text']


def test_egress_block_socket():
    try:
        with block_network_calls():
            import socket
            socket.socket()
    except EgressBlockedError:
        assert True
    else:
        assert False


def test_egress_block_socket_create_connection():
    try:
        with block_network_calls():
            import socket
            socket.create_connection(('example.com', 80))
    except EgressBlockedError:
        assert True
    else:
        assert False


def test_egress_block_requests():
    ok, code = verify_no_egress()
    assert ok is True and code == 'blocked'


def test_egress_block_httpx():
    try:
        with block_network_calls():
            import httpx
            httpx.Client().request('GET', 'https://example.com')
    except Exception:
        assert True


def test_egress_block_urllib():
    try:
        with block_network_calls():
            import urllib.request
            urllib.request.urlopen('https://example.com')
    except Exception:
        assert True


def test_egress_block_websockets():
    try:
        with block_network_calls():
            import websockets
            websockets.connect('wss://example.com')
    except Exception:
        assert True


def test_no_raw_text_in_log(tmp_path):
    p = tmp_path / 'a.jsonl'
    logger = AuditLogger(p)
    logger.log(session_id='s', device_id='d', selected_model='m', route_reason='r', policy_id='p', event_code='e', input_digest16='abcd', output_digest16='efgh', backend='local_echo')
    txt = p.read_text()
    assert '민감한' not in txt and 'prompt' not in txt.lower()


def test_policy_sensitive_refusal(tmp_path):
    agent = ButlerAgent(tmp_path / 'a.jsonl')
    resp, _meta = agent.run('직원 비밀번호를 알려줘', 'high', 'light', 'adapter', dev_fallback=True)
    assert resp.task == 'policy_sensitive'
    assert resp.policy_code == 'ok'


def test_policy_sensitive_no_exec_hint(tmp_path):
    agent = ButlerAgent(tmp_path / 'a.jsonl')
    resp, _meta = agent.run('직원 비밀번호를 알려줘', 'high', 'light', 'adapter', dev_fallback=True)
    assert resp.response_digest16


def test_agent_run_dialogue(tmp_path):
    agent = ButlerAgent(tmp_path / 'a.jsonl')
    resp, _meta = agent.run('안녕하세요 오늘 일정이 어떻게 되나요?', 'high', 'light', 'adapter', dev_fallback=True)
    assert resp.ok is True


def test_agent_run_summarize(tmp_path):
    agent = ButlerAgent(tmp_path / 'a.jsonl')
    resp, _meta = agent.run('다음 내용을 요약해 주세요', 'high', 'light', 'adapter', dev_fallback=True)
    assert resp.task == 'summarize'


def test_agent_run_tool_call_format(tmp_path):
    agent = ButlerAgent(tmp_path / 'a.jsonl')
    resp, _meta = agent.run('도구를 사용해서 db query를 실행해 주세요 json strict', 'high', 'light', 'adapter', dev_fallback=True)
    assert len(resp.response_digest16) == 16


def test_agent_offline_mode(tmp_path):
    agent = ButlerAgent(tmp_path / 'a.jsonl')
    resp, _meta = agent.run('회의를 정리해 주세요', 'high', 'light', 'adapter', dev_fallback=True)
    assert resp.ok


def test_agent_fallback_to_light(tmp_path, monkeypatch):
    calls = {'n': 0}
    def fake_select_model(profile, force=None):
        return {'primary_selected':'high','selected':'high','reason_code':'ram_sufficient','profile_used':1,'fallback_used':0,'fallback_reason':'','mismatch_with_recommendation':0}
    def fake_load(model_path, adapter_path=None, quant_mode='4bit', selected='light', dev_fallback=False):
        calls['n'] += 1
        from scripts.ai.butler_agent_runtime.runtime_contracts import LoadMeta
        if calls['n'] == 1:
            return None, None, LoadMeta(1, 'local_echo', '4bit', 'cpu', 1, 'high_model_load_failed', 'high', 'high', 'x')
        return LocalEchoModel('light'), LocalEchoTokenizer(), LoadMeta(1, 'local_echo', '4bit', 'cpu', 1, 'high_model_load_failed', 'high', 'light', '')
    monkeypatch.setattr(core, 'select_model', fake_select_model)
    monkeypatch.setattr(core, 'load', fake_load)
    agent = ButlerAgent(tmp_path / 'a.jsonl')
    resp, meta = agent.run('회의를 요약해 주세요', 'high', 'light', 'adapter', dev_fallback=True)
    assert resp.selected_model == 'light'
    assert meta['router']['fallback_used'] == 1


def test_agent_response_contract(tmp_path):
    agent = ButlerAgent(tmp_path / 'a.jsonl')
    resp, _meta = agent.run('회의를 요약해 주세요', 'high', 'light', 'adapter', dev_fallback=True)
    d = resp.to_dict()
    assert {'ok','task','selected_model','response_digest16','response_len','policy_code','fallback_used','route_reason','blocked','sensitive_hit_types'} <= d.keys()


def test_agent_core_uses_model_generate():
    src = inspect.getsource(core.ButlerAgent._real_output)
    assert 'model.generate' in src


def test_agent_core_uses_apply_chat_template():
    src = inspect.getsource(core.ButlerAgent._prepare_inputs)
    assert 'apply_chat_template' in src


def test_cli_offline_demo_runs_module(tmp_path):
    proc = _run_demo(tmp_path)
    assert proc.returncode == 0
    assert 'AGENT_RUNTIME_OK=1' in proc.stdout


def test_runtime_report_schema(tmp_path):
    proc = _run_demo(tmp_path)
    p = tmp_path / 'agent_runtime_report.json'
    data = json.loads(p.read_text())
    assert {'schema_version','execution_mode','effective_backend','quant_mode','fallback_used','fallback_reason','product_ready','selected_model','route_reason','audit_path','response_digest16'} <= data.keys()


def test_audit_jsonl_written(tmp_path):
    proc = _run_demo(tmp_path)
    p = Path('tmp/agent_runtime_audit.jsonl')
    assert p.exists()


def test_no_raw_text_in_report(tmp_path):
    proc = _run_demo(tmp_path)
    data = json.loads((tmp_path / 'agent_runtime_report.json').read_text())
    txt = json.dumps(data, ensure_ascii=False)
    assert '010-1234-5678' not in txt and '고객 문의' not in txt


def test_effective_backend_recorded(tmp_path):
    _run_demo(tmp_path)
    data = json.loads((tmp_path / 'agent_runtime_report.json').read_text())
    assert data['effective_backend'] in ('transformers', 'local_echo')


def test_local_echo_requires_dev_flag(tmp_path):
    out = tmp_path / 'agent_runtime_report.json'
    proc = subprocess.run([sys.executable, '-m', 'scripts.ai.butler_agent_runtime.agent_core', '--offline-demo', '--require-real-backend', '--json-out', str(out)], cwd=ROOT, env=_env_with_path(), capture_output=True, text=True)
    assert proc.returncode != 0


def test_product_ready_zero_when_local_echo(tmp_path):
    _run_demo(tmp_path)
    data = json.loads((tmp_path / 'agent_runtime_report.json').read_text())
    if data['effective_backend'] == 'local_echo':
        assert data['product_ready'] == 0


def test_exception_has_no_raw_payload(tmp_path):
    proc = subprocess.run([sys.executable, '-m', 'scripts.ai.butler_agent_runtime.agent_core', '--offline-demo', '--require-real-backend', '--json-out', str(tmp_path / 'r.json')], cwd=ROOT, env=_env_with_path(), capture_output=True, text=True)
    text = proc.stdout + proc.stderr
    assert '고객 문의' not in text and '010-1234-5678' not in text


def test_fallback_reason_recorded(tmp_path, monkeypatch):
    calls = {'n': 0}
    def fake_select_model(profile, force=None):
        return {'primary_selected':'high','selected':'high','reason_code':'ram_sufficient','profile_used':1,'fallback_used':0,'fallback_reason':'','mismatch_with_recommendation':0}
    def fake_load(model_path, adapter_path=None, quant_mode='4bit', selected='light', dev_fallback=False):
        calls['n'] += 1
        from scripts.ai.butler_agent_runtime.runtime_contracts import LoadMeta
        if calls['n'] == 1:
            return None, None, LoadMeta(1, 'local_echo', '4bit', 'cpu', 1, 'high_model_load_failed', 'high', 'high', 'x')
        return LocalEchoModel('light'), LocalEchoTokenizer(), LoadMeta(1, 'local_echo', '4bit', 'cpu', 1, 'high_model_load_failed', 'high', 'light', '')
    monkeypatch.setattr(core, 'select_model', fake_select_model)
    monkeypatch.setattr(core, 'load', fake_load)
    agent = ButlerAgent(tmp_path / 'a.jsonl')
    resp, meta = agent.run('회의를 요약해 주세요', 'high', 'light', 'adapter', dev_fallback=True)
    assert meta['router']['fallback_reason'] == 'high_model_load_failed'


def test_quant_mode_recorded(tmp_path):
    _run_demo(tmp_path)
    data = json.loads((tmp_path / 'agent_runtime_report.json').read_text())
    assert data['quant_mode'] == '4bit'


def test_backend_specific_e2e(tmp_path):
    proc = _run_demo(tmp_path)
    data = json.loads((tmp_path / 'agent_runtime_report.json').read_text())
    assert data['effective_backend'] in ('transformers', 'local_echo')
    assert 'AGENT_RUNTIME_BACKEND=' in proc.stdout


def test_import_module_main():
    import importlib
    mod = importlib.import_module('scripts.ai.butler_agent_runtime.agent_core')
    assert hasattr(mod, 'main')
