#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, zipfile, datetime
from pathlib import Path

def main() -> None:
    ap = argparse.ArgumentParser(description='Audit uploaded model zip and emit objective metadata')
    ap.add_argument('--model-zip', required=True)
    ap.add_argument('--out', default='artifacts/current_model_audit.json')
    args = ap.parse_args()

    model_zip = Path(args.model_zip)
    archive_sha256 = hashlib.sha256(model_zip.read_bytes()).hexdigest()
    with zipfile.ZipFile(model_zip) as z:
        mani = json.loads(z.read('output/butler_model_v1/train_run_manifest.json'))
        state = json.loads(z.read('output/butler_model_v1/checkpoint-42/trainer_state.json'))
        adapter_cfg = json.loads(z.read('output/butler_model_v1/adapter_config.json'))
        readme = z.read('output/butler_model_v1/README.md').decode('utf-8')
        chat_template = z.read('output/butler_model_v1/chat_template.jinja').decode('utf-8')
        special_tokens = json.loads(z.read('output/butler_model_v1/special_tokens_map.json'))
        adapter_size = z.getinfo('output/butler_model_v1/adapter_model.safetensors').file_size
        start = datetime.datetime.fromisoformat(mani['start_utc'].replace('Z','+00:00'))
        end = datetime.datetime.fromisoformat(mani['end_utc'].replace('Z','+00:00'))
        training_seconds = (end - start).total_seconds()

    result = {
        'archive_path': str(model_zip),  # BUG-5b fix: archive_path 추가
        'archive_sha256': archive_sha256,
        'base_model': adapter_cfg['base_model_name_or_path'],
        'adapter_type': adapter_cfg['peft_type'],
        'adapter_rank_r': adapter_cfg['r'],
        'lora_alpha': adapter_cfg['lora_alpha'],
        'adapter_size_mb': round(adapter_size / 1024 / 1024, 2),
        'training_seconds': round(training_seconds, 3),
        'global_step': state['global_step'],
        'max_steps': state['max_steps'],
        'eval_steps': state['eval_steps'],
        'best_metric': state['best_metric'],
        'placeholder_count_in_model_card': readme.count('[More Information Needed]'),
        'chat_template_sha256': hashlib.sha256(chat_template.encode('utf-8')).hexdigest(),
        # BUG-5 fix: pad_token이 dict일 수도 있어 안전하게 접근
        'eos_token': (
            special_tokens['eos_token']['content']
            if isinstance(special_tokens.get('eos_token'), dict)
            else special_tokens.get('eos_token', '')
        ),
        'pad_token': (
            special_tokens['pad_token']['content']
            if isinstance(special_tokens.get('pad_token'), dict)
            else special_tokens.get('pad_token', '')
        ),
        'likely_eval_executed': bool(state.get('best_metric') is not None or any('eval_loss' in x for x in state.get('log_history', [])))
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('CURRENT_MODEL_AUDIT_OK=1')

if __name__ == '__main__':
    main()
