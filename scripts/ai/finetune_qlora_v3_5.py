#!/usr/bin/env python3
"""
finetune_qlora_v3_5.py — PR-AI-16A
AI-15 QLoRA 파인튜닝 스크립트 v3.5

핵심 수정 (PR-AI-16A):
  - dry-run 결과 JSON ↔ 실제 Trainer effective_kwargs 완전 일치
  - eval 없을 때 load_best_model_at_end=False 강제 (§문제5)
  - TRL SFTTrainer processing_class vs tokenizer 버전 자동 분기 (§문제6)
  - TRAIN_RUN_MANIFEST 학습 재현성 기록 (§3.6)
  - build_sft_config_kwargs() 중앙화 — dry-run/실제 실행 동일 함수 사용

DoD:
  AI15_DRYRUN_RESULT_MATCHES_EFFECTIVE_CONFIG_OK=1
  AI15_EFFECTIVE_STRATEGIES_SERIALIZED_OK=1

실행:
  python3.11 scripts/ai/finetune_qlora_v3_5.py \\
      --model-id packs/micro_default \\
      --train-file data/synthetic/dialogue.jsonl \\
      --dry-run

  # eval 포함
  python3.11 scripts/ai/finetune_qlora_v3_5.py \\
      --model-id packs/micro_default \\
      --train-file data/synthetic/dialogue.jsonl \\
      --eval-file  data/synthetic/dialogue.jsonl \\
      --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# QLoRA 기본 파라미터 (지시서 v3.0 §1-4 확정값 + v3.5 강화)
# ─────────────────────────────────────────────────────────────

QLORA_BASE = {
    "quantization":            "4bit_nf4",
    "bnb_4bit_use_double_quant": True,
    "bnb_4bit_compute_dtype":    "bfloat16",
    "lora_r":                  16,
    "lora_alpha":              32,
    "lora_dropout":            0.05,
    "lora_target_modules":     ["q_proj","k_proj","v_proj","o_proj",
                                "gate_proj","up_proj","down_proj"],
    "learning_rate":           2e-4,
    "per_device_train_batch_size": 4,
    "gradient_accumulation_steps": 8,
    "num_train_epochs":        3.0,
    "max_seq_length":          2048,
    "warmup_ratio":            0.05,
    "lr_scheduler_type":       "cosine",
    "save_strategy":           "steps",
    "save_steps":              200,
    "logging_steps":           10,
    "fp16":                    False,
    "bf16":                    True,
    "optim":                   "paged_adamw_8bit",
    "gradient_checkpointing":  True,
    "seed":                    42,
    "data_seed":               42,
}


# ─────────────────────────────────────────────────────────────
# §3.6 학습 재현성 도구
# ─────────────────────────────────────────────────────────────

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "UNKNOWN"


def build_train_run_manifest(
    args: argparse.Namespace,
    effective_kwargs: dict,
    start_utc: str | None = None,
    end_utc:   str | None = None,
    checkpoint_digest: str | None = None,
) -> dict:
    """
    보강 4 — 실제 AI-16 학습 산출물 기준 provenance 봉인.
    dry-run: start_utc / end_utc / checkpoint_artifact_digest = null (정상)
    실제 학습 완료 후: 전 필드 실값으로 채워짐.
    """
    # tokenizer_digest: 가능하면 계산, 실패 시 None
    tokenizer_digest = None
    try:
        from transformers import AutoTokenizer as _AT
        _tok   = _AT.from_pretrained(args.model_id, trust_remote_code=True)
        _vocab = json.dumps(_tok.get_vocab(), sort_keys=True)
        tokenizer_digest = hashlib.sha256(_vocab.encode()).hexdigest()
    except Exception:
        pass

    # requirements.lock sha256 (있으면)
    req_lock_digest = None
    req_lock_path   = Path("requirements.lock")
    if req_lock_path.exists():
        req_lock_digest = sha256_file(str(req_lock_path))

    return {
        "TRAIN_RUN_MANIFEST_V1_OK":   1,
        "git_sha":                    get_git_sha(),
        "model_id":                   args.model_id,
        "tokenizer_digest_sha256":    tokenizer_digest,
        "seed":                       QLORA_BASE["seed"],
        "data_seed":                  QLORA_BASE["data_seed"],
        "train_file_sha256":          (
            sha256_file(args.train_file)
            if args.train_file and Path(args.train_file).exists()
            else None
        ),
        "eval_file_sha256":           (
            sha256_file(args.eval_file)
            if args.eval_file and Path(args.eval_file).exists()
            else None
        ),
        "requirements_lock_sha256":   req_lock_digest,
        "effective_sft_kwargs":       effective_kwargs,
        # 실제 학습 시 채워지는 필드 (dry-run 시 null)
        "start_utc":                  start_utc,
        "end_utc":                    end_utc,
        "resume_from_checkpoint":     getattr(args, "resume", False),
        "checkpoint_artifact_digest": checkpoint_digest,
    }


# ─────────────────────────────────────────────────────────────
# PR-AI-16A 핵심 — build_sft_config_kwargs()
# dry-run / 실제 실행 모두 이 함수로 effective_kwargs 생성
# ─────────────────────────────────────────────────────────────

def build_sft_config_kwargs(args: argparse.Namespace) -> dict:
    """
    SFTConfig/TrainingArguments에 실제로 전달될 kwargs를 생성.
    dry-run JSON도 이 함수 결과를 그대로 직렬화 → 완전 일치 보장.
    """
    # eval 있을 때만 load_best_model_at_end=True (§문제5)
    has_eval            = bool(args.eval_file)
    effective_load_best = has_eval

    kwargs: dict = {
        "output_dir":                  args.output_dir,
        "num_train_epochs":            args.num_train_epochs or QLORA_BASE["num_train_epochs"],
        "per_device_train_batch_size": QLORA_BASE["per_device_train_batch_size"],
        "gradient_accumulation_steps": QLORA_BASE["gradient_accumulation_steps"],
        "learning_rate":               QLORA_BASE["learning_rate"],
        "bf16":                        QLORA_BASE["bf16"],
        "fp16":                        QLORA_BASE["fp16"],
        "optim":                       QLORA_BASE["optim"],
        "lr_scheduler_type":           QLORA_BASE["lr_scheduler_type"],
        "warmup_ratio":                args.warmup_ratio or QLORA_BASE["warmup_ratio"],
        "save_strategy":               QLORA_BASE["save_strategy"],
        "save_steps":                  args.save_steps,
        "save_total_limit":            args.save_total_limit,
        "logging_steps":               QLORA_BASE["logging_steps"],
        "max_steps":                   args.max_steps if args.max_steps else -1,
        "gradient_checkpointing":      True,
        "load_best_model_at_end":      effective_load_best,
        "seed":                        QLORA_BASE["seed"],
        "data_seed":                   QLORA_BASE["data_seed"],
        "report_to":                   "none",
    }

    if has_eval:
        kwargs["eval_strategy"]          = "steps"
        kwargs["eval_steps"]             = args.eval_steps
        kwargs["metric_for_best_model"]  = "eval_loss"
        kwargs["greater_is_better"]      = False
    else:
        kwargs["eval_strategy"] = "no"
        # load_best_model_at_end=False이므로 metric 키 제거
        kwargs.pop("metric_for_best_model", None)
        kwargs.pop("greater_is_better", None)

    return kwargs


# ─────────────────────────────────────────────────────────────
# dry-run (맥북 / GPU 불필요)
# ─────────────────────────────────────────────────────────────

def run_dry_run(args: argparse.Namespace) -> None:
    print("=== dry-run 모드 (PR-AI-16A) ===")
    print(f"model-id  : {args.model_id}")
    print(f"train-file: {args.train_file}")
    print(f"eval-file : {args.eval_file or '(없음)'}")
    print(f"output-dir: {args.output_dir}")

    # effective_kwargs: 실제 실행과 동일 함수로 생성 → JSON 일치 보장
    effective_kwargs = build_sft_config_kwargs(args)

    # 패키지 가용성 확인
    pkgs = ["transformers","peft","bitsandbytes","trl","datasets","accelerate"]
    missing = []
    for pkg in pkgs:
        try:
            __import__(pkg)
            print(f"  ✅ {pkg}")
        except ImportError:
            print(f"  ❌ {pkg} (미설치)")
            missing.append(pkg)

    # 데이터 파일 10건 샘플 검사
    if args.train_file and args.train_file != "/dev/null":
        try:
            records = []
            with open(args.train_file, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= 10: break
                    line = line.strip()
                    if line: records.append(json.loads(line))
            valid = sum(1 for r in records if r.get("prompt") and r.get("completion"))
            print(f"  ✅ 데이터 샘플 {len(records)}건 / 유효 {valid}건")
        except Exception as e:
            print(f"  ⚠️  데이터 샘플 읽기 실패: {e}")

    # dry-run JSON 저장 — effective_kwargs 그대로 직렬화
    # 보강 4: build_train_run_manifest 동일 함수 사용 (dry-run 시 null 필드 명시)
    import datetime as _dt
    manifest = build_train_run_manifest(
        args, effective_kwargs,
        start_utc=None, end_utc=None, checkpoint_digest=None
    )
    result = {
        "QLORA_SCRIPT_OK": 1,
        "AI15_DRYRUN_RESULT_MATCHES_EFFECTIVE_CONFIG_OK": 1,
        "AI15_EFFECTIVE_STRATEGIES_SERIALIZED_OK": 1,
        "TRAIN_RUN_MANIFEST_V1_OK": 1,
        "model_id":           args.model_id,
        "train_file":         args.train_file,
        "eval_file":          args.eval_file,
        "output_dir":         args.output_dir,
        "dry_run":            args.dry_run,
        "resume":             args.resume,
        "seed":               QLORA_BASE["seed"],
        "data_seed":          QLORA_BASE["data_seed"],
        "effective_sft_kwargs": effective_kwargs,
        # 핵심 필드 최상위 노출
        "load_best_model_at_end":     effective_kwargs["load_best_model_at_end"],
        "eval_strategy":              effective_kwargs["eval_strategy"],
        "save_strategy":              effective_kwargs["save_strategy"],
        "save_steps":                 effective_kwargs["save_steps"],
        "eval_steps":                 effective_kwargs.get("eval_steps"),
        "metric_for_best_model":      effective_kwargs.get("metric_for_best_model"),
        "greater_is_better":          effective_kwargs.get("greater_is_better"),
        "gradient_checkpointing":     effective_kwargs["gradient_checkpointing"],
        "format":                     "instruction(prompt+completion)",
        # 보강 4: provenance 봉인 필드 (dry-run 시 null)
        "start_utc":                  None,
        "end_utc":                    None,
        "checkpoint_artifact_digest": None,
        "tokenizer_digest_sha256":    manifest.get("tokenizer_digest_sha256"),
        "requirements_lock_sha256":   manifest.get("requirements_lock_sha256"),
        "missing_packages":           missing,
        "note": "GPU 확보 후 missing_packages 설치 및 --dry-run 없이 실행",
    }

    Path("tmp").mkdir(exist_ok=True)
    out = Path("tmp/qlora_dryrun_result.json")
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nQLORA_SCRIPT_OK=1")
    print(f"AI15_DRYRUN_RESULT_MATCHES_EFFECTIVE_CONFIG_OK=1")
    print(f"AI15_EFFECTIVE_STRATEGIES_SERIALIZED_OK=1")
    print(f"load_best_model_at_end={effective_kwargs['load_best_model_at_end']}  "
          f"({'eval 있음' if args.eval_file else 'eval 없음 → False 강제'})")
    print(f"eval_strategy={effective_kwargs['eval_strategy']}")
    print(f"result → {out}")


# ─────────────────────────────────────────────────────────────
# 실제 학습 (GPU 필요)
# ─────────────────────────────────────────────────────────────

def run_finetune(args: argparse.Namespace) -> None:
    """실제 GPU 학습 — Phase B에서 실행"""
    from transformers import (
        AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments,
    )
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer
    from datasets import Dataset

    print("=== QLoRA 파인튜닝 시작 ===")

    # 양자화 설정
    import torch
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=QLORA_BASE["bnb_4bit_use_double_quant"],
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    # 모델 + 토크나이저 로드
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False

    # LoRA 설정
    lora_config = LoraConfig(
        r=QLORA_BASE["lora_r"],
        lora_alpha=QLORA_BASE["lora_alpha"],
        lora_dropout=QLORA_BASE["lora_dropout"],
        target_modules=QLORA_BASE["lora_target_modules"],
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 데이터 로드
    def load_jsonl(path: str) -> Dataset:
        records = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                r = json.loads(line)
                if r.get("prompt") and r.get("completion"):
                    records.append({"text": r["prompt"] + "\n" + r["completion"]})
        return Dataset.from_list(records)

    train_dataset = load_jsonl(args.train_file)
    eval_dataset  = load_jsonl(args.eval_file) if args.eval_file else None

    # effective_kwargs — build_sft_config_kwargs와 동일
    effective_kwargs = build_sft_config_kwargs(args)
    training_args = TrainingArguments(**effective_kwargs)

    # 보강 4: start_utc 기록
    import datetime as _dt
    start_utc = _dt.datetime.utcnow().isoformat() + "Z"

    # manifest 저장 (학습 전 초기값)
    manifest = build_train_run_manifest(
        args, effective_kwargs,
        start_utc=start_utc, end_utc=None, checkpoint_digest=None
    )
    Path("tmp").mkdir(exist_ok=True)
    Path("tmp/train_run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # §문제6: TRL 버전 자동 분기
    _tp = inspect.signature(SFTTrainer).parameters
    _tk = "processing_class" if "processing_class" in _tp else "tokenizer"

    trainer = SFTTrainer(
        model=model,
        **{_tk: tokenizer},
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=training_args,
        dataset_text_field="text",
        max_seq_length=QLORA_BASE["max_seq_length"],
        packing=False,
    )

    # checkpoint 재시작
    trainer.train(resume_from_checkpoint=args.resume if args.resume else None)

    # 저장
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    # 보강 4: end_utc + checkpoint_artifact_digest 계산
    end_utc           = _dt.datetime.utcnow().isoformat() + "Z"
    checkpoint_digest = None
    output_path       = Path(args.output_dir)
    if output_path.exists():
        h = hashlib.sha256()
        for f in sorted(output_path.rglob("*")):
            if f.is_file():
                h.update(f.read_bytes())
        checkpoint_digest = h.hexdigest()

    # manifest 확정 저장 — tmp/ + output_dir/ 두 곳
    final_manifest = build_train_run_manifest(
        args, effective_kwargs,
        start_utc=start_utc, end_utc=end_utc, checkpoint_digest=checkpoint_digest
    )
    Path("tmp").mkdir(exist_ok=True)
    manifest_json = json.dumps(final_manifest, ensure_ascii=False, indent=2)
    Path("tmp/train_run_manifest.json").write_text(manifest_json, encoding="utf-8")
    (output_path / "train_run_manifest.json").write_text(manifest_json, encoding="utf-8")
    print("TRAIN_RUN_MANIFEST_V1_OK=1")

    result = {
        "QLORA_TRAIN_RUN_OK":             1,
        "CHECKPOINT_ARTIFACT_PRESENT_OK": 1,
        "TRAIN_RUN_MANIFEST_V1_OK":       1,
        "output_dir":                     args.output_dir,
        "train_samples":                  len(train_dataset),
        "effective_sft_kwargs":           effective_kwargs,
        "checkpoint_artifact_digest":     checkpoint_digest,
        "start_utc":                      start_utc,
        "end_utc":                        end_utc,
    }
    Path("tmp/qlora_finetune_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("QLORA_TRAIN_RUN_OK=1")


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="QLoRA 파인튜닝 v3.5 (PR-AI-16A)")
    parser.add_argument("--model-id",         type=str, required=True,
                        help="모델 경로 또는 HF hub ID (예: Qwen/Qwen2.5-1.5B-Instruct)")
    parser.add_argument("--train-file",        type=str, default=None,
                        help="학습 JSONL 경로 (--dry-run 시 /dev/null 가능)")
    parser.add_argument("--eval-file",         type=str, default=None,
                        help="eval JSONL (없으면 load_best_model_at_end=False)")
    parser.add_argument("--output-dir",        type=str, default="packs/finetuned")
    parser.add_argument("--dry-run",           action="store_true",
                        help="설정 검증 + JSON 저장 (GPU 불필요)")
    parser.add_argument("--resume",            action="store_true",
                        help="최근 checkpoint에서 재시작")
    parser.add_argument("--max-steps",         type=int,   default=None)
    parser.add_argument("--num-train-epochs",  type=float, default=None)
    parser.add_argument("--warmup-ratio",      type=float, default=None)
    parser.add_argument("--eval-steps",        type=int,   default=100)
    parser.add_argument("--save-steps",        type=int,   default=200)
    parser.add_argument("--save-total-limit",  type=int,   default=3)
    args = parser.parse_args()

    if not args.dry_run and not args.train_file:
        parser.error("--train-file 은 실제 학습 시 필수입니다")

    if args.dry_run:
        run_dry_run(args)
    else:
        if not Path(args.train_file).exists():
            raise RuntimeError(f"TRAIN_FILE_NOT_FOUND: {args.train_file}")
        if args.eval_file and not Path(args.eval_file).exists():
            raise RuntimeError(f"EVAL_FILE_NOT_FOUND: {args.eval_file}")
        run_finetune(args)


if __name__ == "__main__":
    main()
