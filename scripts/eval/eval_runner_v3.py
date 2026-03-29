from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.eval.eval_dataset_validator_v1 import validate_eval_dataset
from scripts.eval.eval_judge_v3 import run_full_eval


EXIT_EVAL_PASS = 0
EXIT_EVAL_FAIL = 1
EXIT_STRUCTURE_OR_INPUT_ERROR = 2


def load_eval_records(path: Path) -> list:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> int:
    ap = argparse.ArgumentParser(description="Butler 세계 수준 배포 게이트 엔진 v6")
    ap.add_argument("--adapter-dir", default="output/butler_model_small_v1")
    ap.add_argument("--eval-file", default="data/eval/butler_eval_v3.jsonl")
    ap.add_argument("--hardcase-file", default="data/eval/butler_hardcase_v1.jsonl")
    ap.add_argument("--model-version", default="butler_model_small_v1")
    ap.add_argument("--baseline-path", default="data/eval/baseline_scores_v3.json")
    ap.add_argument("--report-path", default="tmp/eval_report_v3.json")
    ap.add_argument("--train-digest-file", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    eval_path = Path(args.eval_file)
    hardcase_path = Path(args.hardcase_file)

    dataset_validation = validate_eval_dataset(str(eval_path), train_digest_file=args.train_digest_file)
    if not dataset_validation.ok:
        print("ERROR: dataset validation failed", file=sys.stderr)
        for reason in dataset_validation.fail_reasons:
            print(f"  -> {reason}", file=sys.stderr)
        return EXIT_STRUCTURE_OR_INPUT_ERROR

    if not hardcase_path.exists():
        print(f"ERROR: hard-case 파일 없음: {hardcase_path}", file=sys.stderr)
        return EXIT_STRUCTURE_OR_INPUT_ERROR

    if args.dry_run:
        result = run_full_eval(
            None,
            None,
            [],
            model_version=args.model_version,
            dry_run=True,
            baseline_path=args.baseline_path,
            eval_set_path=args.eval_file,
            hardcase_file=args.hardcase_file,
            dataset_validation=dataset_validation.__dict__,
            report_path=args.report_path,
        )
        return EXIT_EVAL_PASS if result.passed else EXIT_EVAL_FAIL

    adapter_path = Path(args.adapter_dir)
    if not (adapter_path / "adapter_model.safetensors").exists():
        print(f"ERROR: 어댑터 없음: {adapter_path}", file=sys.stderr)
        return EXIT_STRUCTURE_OR_INPUT_ERROR
    if not eval_path.exists():
        print(f"ERROR: 평가 파일 없음: {eval_path}", file=sys.stderr)
        return EXIT_STRUCTURE_OR_INPUT_ERROR

    try:
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
    except Exception as exc:
        print(f"ERROR: real-run 필수 패키지 로드 실패: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE_OR_INPUT_ERROR

    base_id = "Qwen/Qwen3-4B"
    print(f"모델 로드 중: {adapter_path} (base={base_id})")
    try:
        tokenizer = AutoTokenizer.from_pretrained(base_id, trust_remote_code=True)
        if getattr(tokenizer, "pad_token", None) is None and getattr(tokenizer, "eos_token", None):
            tokenizer.pad_token = tokenizer.eos_token
        use_cuda = bool(torch.cuda.is_available())
        base = AutoModelForCausalLM.from_pretrained(
            base_id,
            trust_remote_code=True,
            torch_dtype=torch.bfloat16 if use_cuda else torch.float32,
            device_map="auto" if use_cuda else None,
            low_cpu_mem_usage=True,
        )
        model = PeftModel.from_pretrained(base, str(adapter_path))
        model.eval()
    except Exception as exc:
        print(f"ERROR: 모델 로드 실패: {exc}", file=sys.stderr)
        return EXIT_STRUCTURE_OR_INPUT_ERROR

    eval_records = load_eval_records(eval_path)
    result = run_full_eval(
        model,
        tokenizer,
        eval_records,
        model_version=args.model_version,
        dry_run=False,
        baseline_path=args.baseline_path,
        eval_set_path=args.eval_file,
        hardcase_file=args.hardcase_file,
        dataset_validation=dataset_validation.__dict__,
        report_path=args.report_path,
    )
    return EXIT_EVAL_PASS if result.passed else EXIT_EVAL_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
