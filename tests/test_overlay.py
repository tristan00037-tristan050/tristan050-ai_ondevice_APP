from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_py(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_overlay_dry_run_and_apply_and_rollback(tmp_path: Path) -> None:
    repo = tmp_path / 'repo'
    (repo / 'scripts' / 'ai').mkdir(parents=True, exist_ok=True)
    target = repo / 'scripts' / 'ai' / 'legacy.py'
    target.write_text(
        "MODEL='Qwen/Qwen2.5-1.5B-Instruct'\nNAME='butler_model_micro_v1'\n",
        encoding='utf-8',
    )

    script = ROOT / 'scripts' / 'cloud' / 'apply_small_overlay_v1.py'

    dry = run_py(str(script), '--repo-dir', str(repo), '--dry-run', cwd=ROOT)
    assert dry.returncode == 0, dry.stderr
    assert ('AI20_OVERLAY_DRY_OK' + '=1') in dry.stdout

    apply = run_py(str(script), '--repo-dir', str(repo), cwd=ROOT)
    assert apply.returncode == 0, apply.stderr
    assert ('AI20_OVERLAY_APPLY_OK' + '=1') in apply.stdout
    changed = target.read_text(encoding='utf-8')
    assert 'Qwen/Qwen3-4B' in changed
    assert 'butler_model_small_v1' in changed

    rollback = run_py(str(script), '--repo-dir', str(repo), '--rollback', cwd=ROOT)
    assert rollback.returncode == 0, rollback.stderr
    assert ('AI20_OVERLAY_ROLLBACK_OK' + '=1') in rollback.stdout
    restored = target.read_text(encoding='utf-8')
    assert 'Qwen/Qwen2.5-1.5B-Instruct' in restored
    assert 'butler_model_micro_v1' in restored


def test_overlay_writes_json(tmp_path: Path) -> None:
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'file.txt').write_text('Qwen/Qwen2.5-7B-Instruct', encoding='utf-8')
    script = ROOT / 'scripts' / 'cloud' / 'apply_small_overlay_v1.py'

    dry = run_py(str(script), '--repo-dir', str(repo), '--dry-run', cwd=ROOT)
    assert dry.returncode == 0
    payload = json.loads((repo / 'tmp/ai20_overlay_dryrun_result.json').read_text(encoding='utf-8'))
    assert payload['mode'] == 'dry-run'
    assert payload['changed_files_count'] == 1
