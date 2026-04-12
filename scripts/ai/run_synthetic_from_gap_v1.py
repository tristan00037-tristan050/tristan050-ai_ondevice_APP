from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPT_MAP = {
    'tool_call': 'scripts/ai/generate_synthetic_tool_call_v2.py',
    'rewrite': 'scripts/ai/generate_synthetic_rewrite_v2.py',
    'retrieval_transform': 'scripts/ai/generate_synthetic_retrieval_v2.py',
}


def _load_gap(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'RUN_FROM_GAP_FAIL=1 reason=gap_file_error:{e}')
        raise SystemExit(2)
    if not isinstance(data, dict):
        print('RUN_FROM_GAP_FAIL=1 reason=gap_file_not_object')
        raise SystemExit(2)
    return data


def _ensure_output_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f'RUN_FROM_GAP_FAIL=1 reason=output_dir_error:{e}')
        raise SystemExit(2)


def run_generation(fn: str, target: int, output: str, dry_run: bool, api_key: str | None) -> tuple[bool, str | None]:
    script = SCRIPT_MAP[fn]
    actual_target = 10 if dry_run else target
    cmd = ['python3', script, '--target', str(actual_target), '--output', output]
    if dry_run:
        cmd += ['--dry-run']
    else:
        cmd += ['--use-batches', 'true']
    if api_key:
        cmd += ['--api-key', api_key]

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    log_path = Path(output).parent / f'{fn}_subprocess.log'
    log_path.write_text((result.stdout or '') + (result.stderr or ''), encoding='utf-8')

    if result.returncode != 0:
        return False, f'subprocess_returncode={result.returncode}'
    out_path = Path(output)
    if not out_path.exists():
        return False, 'output_file_not_created'
    with out_path.open(encoding='utf-8') as f:
        count = sum(1 for _ in f)
    if dry_run and count < 10:
        return False, f'dry_run_count_too_low={count}'
    print(f'SYNTHETIC_{fn.upper()}_COUNT={count}')
    return True, None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--gap-file', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--api-key', default=None)
    args = ap.parse_args()

    gap = _load_gap(Path(args.gap_file))
    _ensure_output_dir(Path(args.output_dir))

    for fn, info in gap.items():
        if not isinstance(info, dict):
            print(f'RUN_FROM_GAP_FAIL=1 reason=invalid_info:{fn}')
            raise SystemExit(2)
        g = info.get('gap', 0)
        action = info.get('action', 'none')
        if not isinstance(g, (int, float)):
            print(f'RUN_FROM_GAP_FAIL=1 reason=invalid_gap_type:{fn}')
            raise SystemExit(2)
        if action not in ('synthetic', 'none'):
            print(f'RUN_FROM_GAP_FAIL=1 reason=invalid_action:{fn}')
            raise SystemExit(2)
        if fn not in SCRIPT_MAP:
            print(f'SKIP_UNKNOWN_FUNCTION {fn}')
            continue
        if action != 'synthetic' or g <= 0:
            print(f'SKIP {fn}: action={action} gap={g}')
            continue
        print(f'RUN {fn}: target={g}')
        output = str(Path(args.output_dir) / f'{fn}_synthetic.jsonl')
        ok, reason = run_generation(fn, int(g), output, args.dry_run, args.api_key)
        if not ok:
            print(f'RUN_FROM_GAP_FAIL=1 reason={fn} {reason}')
            raise SystemExit(1)
    print('RUN_FROM_GAP_COMPLETE=1')


if __name__ == '__main__':
    main()
