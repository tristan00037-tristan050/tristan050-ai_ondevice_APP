#!/usr/bin/env python3
from __future__ import annotations
import argparse, inspect, json, hashlib, subprocess, sys, datetime, importlib.util
from pathlib import Path

BASE_DEFAULTS = {
    'seed': 42,
    'data_seed': 42,
    'max_seq_length': 2048,  # BUG-4 fix: finetune_qlora_v3_5.py와 통일
    'bf16': True,
    'fp16': False,
    'optim': 'paged_adamw_8bit',
    'lr_scheduler_type': 'cosine',
    'per_device_train_batch_size': 4,
    'gradient_accumulation_steps': 8,
    'learning_rate': 2e-4,
    'warmup_ratio': 0.05,
    'save_strategy': 'steps',
    'save_steps': 200,
    'save_total_limit': 3,
    'logging_steps': 10,
    'gradient_checkpointing': True,
    'report_to': 'none',
}
REQ_PKGS = ['transformers', 'peft', 'bitsandbytes', 'trl', 'datasets', 'accelerate']

def sha256_file(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def get_git_sha() -> str:
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return 'UNKNOWN'

def missing_packages() -> list[str]:
    out = []
    for name in REQ_PKGS:
        if importlib.util.find_spec(name) is None:
            out.append(name)
    return out

def build_sft_kwargs(args) -> dict:
    kwargs = {
        'output_dir': args.output_dir,
        'max_seq_length': BASE_DEFAULTS['max_seq_length'],  # BUG-4 fix
        'num_train_epochs': args.num_train_epochs,
        'seed': BASE_DEFAULTS['seed'],
        'data_seed': BASE_DEFAULTS['data_seed'],
        **BASE_DEFAULTS,
    }
    if args.eval_file:
        kwargs.update({
            'load_best_model_at_end': True,
            'eval_strategy': 'steps',
            'eval_steps': args.eval_steps,
            'metric_for_best_model': 'eval_loss',
            'greater_is_better': False,
        })
    else:
        kwargs.update({
            'load_best_model_at_end': False,
            'eval_strategy': 'no',
        })
    return kwargs

def build_train_run_manifest(args, effective_kwargs: dict, start_utc=None, end_utc=None, checkpoint_digest=None) -> dict:
    tokenizer_digest = None
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(args.model_id)
        vocab = json.dumps(tok.get_vocab(), sort_keys=True)
        tokenizer_digest = hashlib.sha256(vocab.encode()).hexdigest()
    except Exception:
        pass
    # BUG-3 fix: requirements_lock_sha256 추가 (finetune_qlora_v3_5.py 스키마 통일)
    req_lock_digest = None
    req_lock_path = Path('requirements.lock')
    if req_lock_path.exists():
        import hashlib as _hl
        req_lock_digest = _hl.sha256(req_lock_path.read_bytes()).hexdigest()

    return {
        'TRAIN_RUN_MANIFEST_V1_OK': 1,
        'git_sha': get_git_sha(),
        'model_id': args.model_id,
        'tokenizer_digest_sha256': tokenizer_digest,
        'seed': BASE_DEFAULTS['seed'],
        'data_seed': BASE_DEFAULTS['data_seed'],
        'requirements_lock_sha256': req_lock_digest,  # BUG-3 fix
        'train_file_sha256': sha256_file(args.train_file),
        'eval_file_sha256': sha256_file(args.eval_file),
        'effective_sft_kwargs': effective_kwargs,
        'start_utc': start_utc,
        'end_utc': end_utc,
        'resume_from_checkpoint': args.resume,
        'checkpoint_artifact_digest': checkpoint_digest,
    }

def main() -> None:
    ap = argparse.ArgumentParser(description='World-class student QLoRA launcher')
    ap.add_argument('--model-id', default='Qwen/Qwen2.5-1.5B-Instruct')
    ap.add_argument('--train-file', required=True)
    ap.add_argument('--eval-file')
    ap.add_argument('--output-dir', default='output/student_worldclass_v1')
    ap.add_argument('--num-train-epochs', type=float, default=2.0)
    ap.add_argument('--eval-steps', type=int, default=100)
    ap.add_argument('--resume')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    eff = build_sft_kwargs(args)
    manifest = build_train_run_manifest(args, eff)
    out = Path('tmp/worldclass_student_qlora_dryrun.json')
    out.parent.mkdir(parents=True, exist_ok=True)

    pkgs_missing = missing_packages()
    payload = {
        'dry_run': args.dry_run,
        'effective_sft_kwargs': eff,
        'train_run_manifest': manifest,
        'note': 'Run without --dry-run on a GPU host to produce checkpoints.',
    }

    if pkgs_missing:
        payload['status'] = 'MISSING_DEPENDENCIES'
        payload['missing_packages'] = pkgs_missing
        payload['ready'] = False
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'WORLDCLASS_STUDENT_QLORA_NOT_READY: missing {pkgs_missing}', file=sys.stderr)
        sys.exit(1)
    else:
        payload['status'] = 'READY'
        payload['missing_packages'] = []
        payload['ready'] = True
        payload['WORLDCLASS_STUDENT_QLORA_READY_OK'] = 1
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print('WORLDCLASS_STUDENT_QLORA_READY_OK=1')
        sys.exit(0)

if __name__ == '__main__':
    main()
