#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, datetime
from pathlib import Path


def run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, text=True, capture_output=True, cwd=cwd)
    return p.returncode, p.stdout + p.stderr

def main() -> None:
    ap = argparse.ArgumentParser(description='Run a full continual autolearn cycle')
    ap.add_argument('--root', default='.')
    ap.add_argument('--model-id', default='Qwen/Qwen2.5-1.5B-Instruct',
                    help='학습에 사용할 student 모델 ID')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    root = Path(args.root).resolve()
    cycle_id = datetime.datetime.utcnow().strftime('cycle_%Y%m%dT%H%M%SZ')
    cycle_dir = root / 'autolearn' / 'cycles' / cycle_id
    dataset_dir = cycle_dir / 'dataset'
    cycle_dir.mkdir(parents=True, exist_ok=True)

    steps = []
    commands = [
        ['python3', str(root/'scripts/upgrade/normalize_and_score_incoming_v1.py'), '--incoming-dir', str(root/'autolearn/incoming'), '--out', str(cycle_dir/'normalized.jsonl')],
        ['python3', str(root/'scripts/upgrade/self_instruct_expander_v1.py'), '--out', str(cycle_dir/'self_instruct.jsonl'), '--count', '60'],
        ['python3', str(root/'scripts/upgrade/replay_buffer_manager_v1.py'), '--incoming', str(cycle_dir/'normalized.jsonl'), '--replay', str(root/'autolearn/replay/replay_buffer.jsonl'), '--out', str(cycle_dir/'replay_merged.jsonl')],
        ['python3', str(root/'scripts/upgrade/build_incremental_dataset_v1.py'), '--primary', str(cycle_dir/'replay_merged.jsonl'), '--secondary', str(cycle_dir/'self_instruct.jsonl'), '--out-dir', str(dataset_dir)],
        ['python3', str(root/'scripts/ai/verify_train_input_v1.py'), '--train', str(dataset_dir/'train.jsonl'), '--val', str(dataset_dir/'validation.jsonl'), '--test', str(dataset_dir/'test.jsonl'), '--json-out', str(cycle_dir/'sanity_result.json')],
        # BUG-1 fix: --dry-run을 args.dry_run에 따라 조건부 전달
        # BUG-2 fix: --model-id 추가 전달
        (['python3', str(root/'scripts/upgrade/train_student_qlora_worldclass_v1.py'),
          '--model-id', args.model_id,
          '--train-file', str(dataset_dir/'train.jsonl'),
          '--eval-file', str(dataset_dir/'validation.jsonl'),
          '--output-dir', str(cycle_dir/'student_output')]
         + (['--dry-run'] if args.dry_run else [])),
    ]
    for cmd in commands:
        rc, out = run(cmd, cwd=str(root))
        steps.append({'cmd': cmd, 'returncode': rc, 'output': out})
        if rc != 0:
            break

    promote_path = cycle_dir / 'promotion_decision.json'
    if all(s['returncode'] == 0 for s in steps):
        rc, out = run(['python3', str(root/'scripts/upgrade/evaluate_and_promote_v1.py'), '--sanity-json', str(cycle_dir/'sanity_result.json'), '--out', str(promote_path)], cwd=str(root))
        steps.append({'cmd': ['python3', str(root/'scripts/upgrade/evaluate_and_promote_v1.py')], 'returncode': rc, 'output': out})

    manifest = {
        'AUTOLEARN_CYCLE_OK': int(all(s['returncode'] == 0 for s in steps)),
        'cycle_id': cycle_id,
        'dry_run': args.dry_run,
        'steps': steps,
    }
    (cycle_dir/'cycle_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"AUTOLEARN_CYCLE_OK={manifest['AUTOLEARN_CYCLE_OK']}")
    print(f'CYCLE_DIR={cycle_dir}')

if __name__ == '__main__':
    main()
