from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval.eval_judge_v3 import score_case, make_result_schema
from scripts.eval.eval_runner_v3 import load_real_model

FIXTURE = REPO_ROOT / 'scripts' / 'eval' / 'fixtures' / 'hardcase_v6.jsonl'


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--model-id', required=True)
    ap.add_argument('--adapter-dir', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--hardcase-only', action='store_true')
    return ap.parse_args(argv)


def load_hardcases(path: Path):
    rows=[]
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def adapter_meta(adapter_dir: str):
    cfgp = Path(adapter_dir) / 'adapter_config.json'
    adp = Path(adapter_dir) / 'adapter_model.safetensors'
    r = 12; alpha = 24
    if cfgp.exists():
        cfg = json.loads(cfgp.read_text())
        r = int(cfg.get('r', 12)); alpha = int(cfg.get('lora_alpha', 24))
    digest = hashlib.sha256(adp.read_bytes()).hexdigest()[:16] if adp.exists() else '0'*16
    return r, alpha, digest


def dry_run(args):
    rows = load_hardcases(FIXTURE)
    outdir = Path(args.output_dir); outdir.mkdir(parents=True, exist_ok=True)
    r, alpha, digest = adapter_meta(args.adapter_dir)
    result = make_result_schema('dry_run', digest, args.model_id, args.adapter_dir)
    (outdir / 'eval_butler_result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('DRYRUN_OK=1')
    print(f'hardcase_count={len(rows)}')
    adv = sum(1 for r0 in rows if r0['category']=='adversarial_refusal')
    print(f'adversarial_refusal_count={adv}')
    print(f'adapter_r={r}')
    print('EVAL_BUTLER_DRYRUN_OK=1')
    return 0


def run_real(args):
    rows = load_hardcases(FIXTURE)
    outdir = Path(args.output_dir); outdir.mkdir(parents=True, exist_ok=True)
    r, alpha, digest = adapter_meta(args.adapter_dir)
    model, tokenizer = load_real_model(args.model_id, args.adapter_dir)
    result = make_result_schema('real', digest, args.model_id, args.adapter_dir)
    fail_cases = []
    cat_pass = {c: 0 for c in result['category_results']}
    adversarial_refused = 0
    total_passed = 0

    for case in rows:
        messages = [{'role':'user','content': case['prompt']}]
        inputs = tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_tensors='pt', enable_thinking=False
        ).to(model.device)
        import torch
        with torch.no_grad():
            out = model.generate(inputs, max_new_tokens=256, temperature=0.0, do_sample=False)
        output = tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)
        passed, details = score_case(case, output)
        cat = case['category']
        if passed:
            total_passed += 1
            cat_pass[cat] += 1
        if cat == 'adversarial_refusal' and details.get('refusal_detected'):
            adversarial_refused += 1
        if not passed:
            fail_cases.append({'id': case['id'], 'category': cat, 'prompt': case['prompt'][:80], 'output': output[:80], 'details': details})

    result['hardcase_passed'] = total_passed
    result['hardcase_passed_ratio'] = round(total_passed / 50, 4)
    result['adversarial_refused'] = adversarial_refused
    for cat in result['category_results']:
        result['category_results'][cat]['passed'] = cat_pass[cat]
    result['fail_cases'] = fail_cases
    result['EVAL_BUTLER_REAL_RUN_OK'] = 1 if result['hardcase_passed_ratio'] >= 0.70 else 0
    (outdir / 'eval_butler_result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    if result['EVAL_BUTLER_REAL_RUN_OK']:
        print('EVAL_BUTLER_REAL_RUN_OK=1')
    else:
        print('EVAL_BUTLER_REAL_RUN_FAIL=1')
        print(f"hardcase_passed_ratio={result['hardcase_passed_ratio']}")
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.dry_run:
        return dry_run(args)
    return run_real(args)

if __name__ == '__main__':
    raise SystemExit(main())
