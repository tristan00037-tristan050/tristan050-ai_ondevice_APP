#!/usr/bin/env python3
"""
run_phase_c_verification_v1.py — Phase C 오케스트레이터 (v52)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, text=True, capture_output=True)
    return p.returncode, p.stdout + p.stderr


def emit_pr_artifacts(dir_path: str, success: bool, dry_run: bool, smoke_path: str, eval_path: str, det_path: str) -> str:
    out_dir = Path(dir_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    note = "real success" if success and not dry_run else "ready only"
    (out_dir / 'PR-AI-16F.md').write_text(
        "# PR-AI-16F\n\n"         f"status: {note}\n"         f"artifact: {smoke_path}\n",
        encoding='utf-8'
    )
    (out_dir / 'PR-AI-12R.md').write_text(
        "# PR-AI-12R\n\n"         f"status: {note}\n"         f"artifact: {eval_path}\n",
        encoding='utf-8'
    )
    (out_dir / 'PR-AI-16F_determinism.md').write_text(
        "# PR-AI-16F DETERMINISM\n\n"         f"status: {note}\n"         f"artifact: {det_path}\n",
        encoding='utf-8'
    )
    (out_dir / 'create_phase_c_prs.sh').write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"         "echo 'Use gh pr create with the generated markdown files.'\n",
        encoding='utf-8'
    )
    return str(out_dir)


def main() -> None:
    ap = argparse.ArgumentParser(description='Run Phase C verification end-to-end')
    ap.add_argument('--adapter-dir', default='output/butler_model_v1')
    ap.add_argument('--eval-file', default='data/phase_c/butler_eval_v1.jsonl')
    ap.add_argument('--schema-file', default='schemas/tool_call_schema_v3.json')
    ap.add_argument('--repeat', type=int, default=3)
    ap.add_argument('--device-preference', default='auto', choices=['auto', 'cuda', 'mps', 'cpu'])
    ap.add_argument('--load-mode', default='auto', choices=['auto', '4bit', 'full'])
    ap.add_argument('--latency-budget-ms', type=float, default=5000.0)
    ap.add_argument('--emit-pr-artifacts-dir', default='tmp/phase_c_pr_artifacts')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--out', default='tmp/phase_c_result.json')
    args = ap.parse_args()

    base = [
        '--adapter-dir', args.adapter_dir,
        '--schema-file', args.schema_file,
        '--device-preference', args.device_preference,
        '--load-mode', args.load_mode,
        '--latency-budget-ms', str(args.latency_budget_ms),
    ]
    if args.dry_run:
        base.append('--dry-run')

    steps = []
    cmds = [
        [sys.executable, 'scripts/verify/verify_phase_c_eval_dataset_v1.py', '--schema', args.schema_file, '--eval-file', args.eval_file],
        [sys.executable, 'scripts/ai/run_smoke_eval_v1.py', *base, '--repeat', str(args.repeat), '--out', 'tmp/smoke_result.json'],
        [sys.executable, 'scripts/ai/eval_butler_v1.py', *base, '--eval-file', args.eval_file, '--out', 'tmp/eval_result.json'],
        [sys.executable, 'scripts/ai/run_determinism_check_v1.py', *base, '--repeat', str(args.repeat), '--out', 'tmp/determinism_result.json'],
    ]

    for cmd in cmds:
        rc, out = run(cmd)
        steps.append({'cmd': cmd, 'returncode': rc, 'output': out})
        print(out)
        if rc != 0:
            break

    ok = int(all(s['returncode'] == 0 for s in steps))
    ready = int(len(steps) == len(cmds) and all(s['returncode'] == 0 for s in steps))
    pr_dir = emit_pr_artifacts(args.emit_pr_artifacts_dir, success=bool(ok), dry_run=args.dry_run,
                               smoke_path='tmp/smoke_result.json', eval_path='tmp/eval_result.json', det_path='tmp/determinism_result.json')
    payload = {
        'PHASE_C_VERIFICATION_READY': ready,
        'PHASE_C_VERIFICATION_OK': ok if not args.dry_run else 0,
        'dry_run': args.dry_run,
        'steps': steps,
        'latency_budget_ms': args.latency_budget_ms,
        'PHASE_C_OK_CONDITION': {
            'dry_run_must_be_false': True,
            'all_steps_returncode_zero': True,
            'smoke_all_runs_pass': 1,
            'eval_butler_ok': 1,
            'determinism_ok': 1,
            'phase_c_eval_dataset_ok': 1,
            'p95_latency_ms_lte_budget': True,
        },
        'PHASE_C_DRY_RUN_REASON': (
            'dry-run은 실제 모델 로드와 추론을 수행하지 않기 때문에 PHASE_C_VERIFICATION_OK가 0으로 유지됩니다. 실제 GPU/모델 환경에서 dry_run=false로 실행해야 1로 바뀝니다.'
            if args.dry_run else None
        ),
        'pr_artifacts_dir': pr_dir,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.dry_run:
        print(f"PHASE_C_VERIFICATION_READY={payload['PHASE_C_VERIFICATION_READY']}")
        print('PHASE_C_VERIFICATION_OK=0 (dry-run by design)')
        if payload['PHASE_C_VERIFICATION_READY'] != 1:
            print('PHASE_C_READY_REASON=one_or_more_steps_failed_even_in_dry_run')
    else:
        print(f"PHASE_C_VERIFICATION_OK={payload['PHASE_C_VERIFICATION_OK']}")
    if not args.dry_run and ok != 1:
        sys.exit(1)


if __name__ == '__main__':
    main()
