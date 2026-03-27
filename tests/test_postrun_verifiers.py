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


def test_postrun_training_only(tmp_path: Path) -> None:
    output_dir = tmp_path / 'output' / 'butler_model_small_v1'
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'adapter_model.safetensors').write_text('not-a-real-model-but-present', encoding='utf-8')
    (output_dir / 'adapter_config.json').write_text(
        json.dumps({'base_model_name_or_path': 'Qwen/Qwen3-4B'}),
        encoding='utf-8',
    )

    proc = run_py(
        'scripts/verify/verify_ai20_server_postrun_v1.py',
        '--mode', 'training-only',
        '--output-dir', str(output_dir),
    )
    assert proc.returncode == 0, proc.stderr
    assert 'AI20_POSTRUN_TRAINING_ONLY_OK=1' in proc.stdout


def test_completion_evidence(tmp_path: Path) -> None:
    output_dir = tmp_path / 'output' / 'butler_model_small_v1'
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'adapter_model.safetensors').write_text('artifact', encoding='utf-8')
    result_file = tmp_path / 'phase_c_result.json'
    result_file.write_text(json.dumps({'PHASE_C_VERIFICATION_OK': 1}), encoding='utf-8')

    proc = run_py(
        'scripts/verify/verify_ai20_completion_evidence_v1.py',
        '--result-file', str(result_file),
        '--output-dir', str(output_dir),
    )
    assert proc.returncode == 0, proc.stderr
    assert 'AI20_COMPLETION_EVIDENCE_OK=1' in proc.stdout
