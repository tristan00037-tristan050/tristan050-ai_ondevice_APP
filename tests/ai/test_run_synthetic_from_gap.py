from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai import run_synthetic_from_gap_v1 as mod


SAMPLE_JSONL_10 = ('{}\n' * 10)
SAMPLE_JSONL_22 = ('{}\n' * 22)


def test_skip_when_gap_zero(tmp_path, capsys, monkeypatch):
    gap = {'tool_call': {'gap': 0, 'action': 'synthetic'}}
    gapf = tmp_path / 'gap.json'
    gapf.write_text(json.dumps(gap), encoding='utf-8')
    called = []
    monkeypatch.setattr(mod, 'run_generation', lambda *a, **k: called.append((a, k)) or (True, None))
    monkeypatch.setattr(sys, 'argv', ['x', '--gap-file', str(gapf), '--output-dir', str(tmp_path / 'out')])
    mod.main()
    out = capsys.readouterr().out
    assert 'SKIP tool_call: action=synthetic gap=0' in out
    assert called == []


def test_skip_when_action_none(tmp_path, capsys, monkeypatch):
    gap = {'rewrite': {'gap': 12, 'action': 'none'}}
    gapf = tmp_path / 'gap.json'
    gapf.write_text(json.dumps(gap), encoding='utf-8')
    monkeypatch.setattr(mod, 'run_generation', lambda *a, **k: (_ for _ in ()).throw(AssertionError('should not run')))
    monkeypatch.setattr(sys, 'argv', ['x', '--gap-file', str(gapf), '--output-dir', str(tmp_path / 'out')])
    mod.main()
    assert 'SKIP rewrite: action=none gap=12' in capsys.readouterr().out


def test_skip_unknown_function(tmp_path, capsys, monkeypatch):
    gap = {'dialogue': {'gap': 11, 'action': 'synthetic'}}
    gapf = tmp_path / 'gap.json'
    gapf.write_text(json.dumps(gap), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['x', '--gap-file', str(gapf), '--output-dir', str(tmp_path / 'out')])
    mod.main()
    assert 'SKIP_UNKNOWN_FUNCTION dialogue' in capsys.readouterr().out


def test_run_when_gap_positive(tmp_path, capsys, monkeypatch):
    gap = {'tool_call': {'gap': 12, 'action': 'synthetic'}}
    gapf = tmp_path / 'gap.json'
    gapf.write_text(json.dumps(gap), encoding='utf-8')
    seen = {}

    def fake_run(fn, target, output, dry_run, api_key):
        seen.update({'fn': fn, 'target': target, 'output': output, 'dry_run': dry_run, 'api_key': api_key})
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(SAMPLE_JSONL_10, encoding='utf-8')
        print('SYNTHETIC_TOOL_CALL_COUNT=10')
        return True, None

    monkeypatch.setattr(mod, 'run_generation', fake_run)
    monkeypatch.setattr(sys, 'argv', ['x', '--gap-file', str(gapf), '--output-dir', str(tmp_path / 'out'), '--dry-run'])
    mod.main()
    out = capsys.readouterr().out
    assert 'RUN tool_call: target=12' in out
    assert 'RUN_FROM_GAP_COMPLETE=1' in out
    assert seen['fn'] == 'tool_call'
    assert seen['target'] == 12
    assert seen['dry_run'] is True


def test_dry_run_flag_passed(tmp_path, monkeypatch):
    out = tmp_path / 'tool.jsonl'
    calls = []

    def fake_subprocess_run(cmd, check, capture_output, text):
        calls.append(cmd)
        out.write_text(SAMPLE_JSONL_10, encoding='utf-8')
        return subprocess.CompletedProcess(cmd, 0, stdout='ok', stderr='')

    monkeypatch.setattr(mod.subprocess, 'run', fake_subprocess_run)
    ok, reason = mod.run_generation('tool_call', 123, str(out), True, 'KEY')
    assert ok and reason is None
    assert '--dry-run' in calls[0]
    assert '--api-key' in calls[0]


def test_use_batches_flag_on_real_run(tmp_path, monkeypatch):
    out = tmp_path / 'rewrite.jsonl'
    calls = []

    def fake_subprocess_run(cmd, check, capture_output, text):
        calls.append(cmd)
        out.write_text(SAMPLE_JSONL_22, encoding='utf-8')
        return subprocess.CompletedProcess(cmd, 0, stdout='ok', stderr='')

    monkeypatch.setattr(mod.subprocess, 'run', fake_subprocess_run)
    ok, reason = mod.run_generation('rewrite', 22, str(out), False, None)
    assert ok and reason is None
    assert '--use-batches' in calls[0] and 'true' in calls[0]
    assert '--dry-run' not in calls[0]


def test_output_dir_created(tmp_path):
    missing = tmp_path / 'newdir'
    mod._ensure_output_dir(missing)
    assert missing.exists() and missing.is_dir()


def test_subprocess_failure_propagates(tmp_path, monkeypatch):
    out = tmp_path / 'retrieval_transform.jsonl'

    def fake_subprocess_run(cmd, check, capture_output, text):
        return subprocess.CompletedProcess(cmd, 9, stdout='bad', stderr='err')

    monkeypatch.setattr(mod.subprocess, 'run', fake_subprocess_run)
    ok, reason = mod.run_generation('retrieval_transform', 22, str(out), False, None)
    assert ok is False
    assert reason == 'subprocess_returncode=9'


def test_compile_script():
    import py_compile
    py_compile.compile(str(ROOT / 'scripts/ai/run_synthetic_from_gap_v1.py'), doraise=True)
