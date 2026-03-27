from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_py(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_finetune_dry_run_creates_json() -> None:
    proc = run_py('scripts/ai/finetune_qlora_small_v1.py', '--dry-run')
    assert proc.returncode == 0, proc.stderr
    assert 'FINETUNE_SMALL_DRY_OK=1' in proc.stdout
    payload = json.loads((ROOT / 'tmp/ai20_finetune_dryrun_result.json').read_text(encoding='utf-8'))
    assert payload['qlora_small_config']['base_model_id'] == 'Qwen/Qwen3-4B'
    assert payload['qwen3_specific']['enable_thinking'] is False


def test_verify_bundle_structure_ok() -> None:
    proc = run_py('scripts/verify/verify_ai20_bundle_readiness_v1.py', '--repo-dir', '.', '--dry-run')
    assert proc.returncode == 0, proc.stderr
    assert 'AI20_BUNDLE_STRUCTURE_OK=1' in proc.stdout
    payload = json.loads((ROOT / 'tmp/ai20_bundle_structure_result.json').read_text(encoding='utf-8'))
    assert payload['AI20_BUNDLE_STRUCTURE_OK'] == 1


def test_shell_syntax_files_exist() -> None:
    for rel in ['scripts/cloud/run_training_small_v1.sh', 'scripts/cloud/run_phase_c_small_v1.sh']:
        assert (ROOT / rel).exists()
