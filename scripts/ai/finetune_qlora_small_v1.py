#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

TARGET_PRESETS: dict[str, dict[str, Any]] = {
    "small_default": {
        "model_id": "Qwen/Qwen2.5-3B-Instruct",
        "model_tag": "small_default",
        "target_vram_gb": 8,
        "max_seq_length": 1536,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 16,
        "learning_rate": 2e-4,
        "num_train_epochs": 3.0,
        "warmup_ratio": 0.05,
        "eval_steps": 50,
        "save_steps": 100,
        "save_total_limit": 3,
    },
    "micro_default": {
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "model_tag": "micro_default",
        "target_vram_gb": 4,
        "max_seq_length": 1024,
        "lora_r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.05,
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 16,
        "learning_rate": 2.5e-4,
        "num_train_epochs": 3.0,
        "warmup_ratio": 0.05,
        "eval_steps": 50,
        "save_steps": 100,
        "save_total_limit": 3,
    },
}

COMMON_DEFAULTS: dict[str, Any] = {
    "quantization": "4bit_nf4",
    "bnb_4bit_use_double_quant": True,
    "bnb_4bit_quant_type": "nf4",
    "gradient_checkpointing": True,
    "optim": "paged_adamw_8bit",
    "lr_scheduler_type": "cosine",
    "save_strategy": "steps",
    "logging_steps": 10,
    "report_to": "none",
    "seed": 42,
    "data_seed": 42,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
}


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "UNKNOWN"


def resolve_preset(args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    preset = dict(TARGET_PRESETS[args.target_tag])
    warnings: list[str] = []
    if args.model_id:
        if args.model_id != preset["model_id"] and not args.allow_model_override:
            raise RuntimeError(
                f"MODEL_TAG_MISMATCH:{args.target_tag}:expected={preset['model_id']}:got={args.model_id}. "
                "커스텀 모델을 쓰려면 --allow-model-override 사용"
            )
        if args.model_id != preset["model_id"]:
            warnings.append(f"model_override={args.model_id}")
        preset["model_id"] = args.model_id
    return preset, warnings


def validate_transformers_version() -> str | None:
    try:
        import transformers
        from packaging.version import Version
        if Version(transformers.__version__) < Version("4.37.0"):
            return f"transformers<{transformers.__version__}> may fail for qwen2; use >=4.37.0"
    except Exception:
        return None
    return None


def detect_missing_packages() -> list[str]:
    missing = []
    for pkg in ["transformers", "peft", "bitsandbytes", "trl", "datasets", "accelerate"]:
        try:
            __import__(pkg)
        except Exception:
            missing.append(pkg)
    return missing


def pick_precision_flags() -> tuple[bool, bool]:
    try:
        import torch
        if torch.cuda.is_available():
            if torch.cuda.is_bf16_supported():
                return True, False
            return False, True
    except Exception:
        pass
    return False, False


def choose_eval_strategy_key() -> tuple[str, bool, str]:
    try:
        from transformers import TrainingArguments
        params = inspect.signature(TrainingArguments).parameters
        if "eval_strategy" in params:
            return "eval_strategy", True, "runtime_inspection"
        if "evaluation_strategy" in params:
            return "evaluation_strategy", True, "runtime_inspection"
        return "eval_strategy", False, "runtime_trainingarguments_unknown"
    except Exception:
        return "eval_strategy", False, "assumed_default_without_transformers"


def enforce_real_train_fail_closed(git_sha: str, strategy_meta: dict[str, Any]) -> None:
    if git_sha == "UNKNOWN":
        raise RuntimeError("REAL_TRAIN_GIT_SHA_RESOLVED_OK=0: git repo 안에서 실행해야 합니다")
    if strategy_meta.get("training_arguments_strategy_key_resolved") is None:
        raise RuntimeError(
            "TRAINING_ARGUMENTS_STRATEGY_KEY_RESOLVED_FOR_REAL_RUN_OK=0: "
            "실제 학습 환경에서 TrainingArguments strategy key가 resolve되어야 합니다"
        )


def build_effective_kwargs(args: argparse.Namespace, preset: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    has_eval = bool(args.eval_file)
    bf16, fp16 = pick_precision_flags()
    strategy_key, strategy_resolved, strategy_source = choose_eval_strategy_key()
    kwargs: dict[str, Any] = {
        "output_dir": args.output_dir,
        "num_train_epochs": args.num_train_epochs or preset["num_train_epochs"],
        "per_device_train_batch_size": preset["per_device_train_batch_size"],
        "gradient_accumulation_steps": preset["gradient_accumulation_steps"],
        "learning_rate": preset["learning_rate"],
        "bf16": bf16,
        "fp16": fp16,
        "optim": COMMON_DEFAULTS["optim"],
        "lr_scheduler_type": COMMON_DEFAULTS["lr_scheduler_type"],
        "warmup_ratio": args.warmup_ratio or preset["warmup_ratio"],
        "save_strategy": COMMON_DEFAULTS["save_strategy"],
        "save_steps": args.save_steps or preset["save_steps"],
        "save_total_limit": args.save_total_limit or preset["save_total_limit"],
        "logging_steps": COMMON_DEFAULTS["logging_steps"],
        "gradient_checkpointing": COMMON_DEFAULTS["gradient_checkpointing"],
        "seed": COMMON_DEFAULTS["seed"],
        "data_seed": COMMON_DEFAULTS["data_seed"],
        "report_to": COMMON_DEFAULTS["report_to"],
        "load_best_model_at_end": has_eval,
        "max_steps": args.max_steps if args.max_steps else -1,
    }
    if has_eval:
        kwargs[strategy_key] = "steps"
        kwargs["eval_steps"] = args.eval_steps or preset["eval_steps"]
        kwargs["metric_for_best_model"] = "eval_loss"
        kwargs["greater_is_better"] = False
    else:
        kwargs[strategy_key] = "no"
    meta = {
        "training_arguments_strategy_key_resolved": strategy_key if strategy_resolved else None,
        "training_arguments_strategy_key_assumed": None if strategy_resolved else strategy_key,
        "training_arguments_strategy_key_resolution_source": strategy_source,
    }
    return kwargs, meta


def compute_tokenizer_digest(model_id: str) -> str | None:
    try:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        return sha256_text(json.dumps(tok.get_vocab(), sort_keys=True))
    except Exception:
        return None


def build_train_run_manifest(
    args: argparse.Namespace,
    preset: dict[str, Any],
    effective_kwargs: dict[str, Any],
    strategy_meta: dict[str, Any],
    start_utc: str | None = None,
    end_utc: str | None = None,
    checkpoint_digest: str | None = None,
) -> dict[str, Any]:
    req_lock = Path("requirements.lock")
    return {
        "TRAIN_RUN_MANIFEST_V1_OK": 1,
        "git_sha": get_git_sha(),
        "model_id": preset["model_id"],
        "model_tag": preset["model_tag"],
        "target_vram_gb": preset["target_vram_gb"],
        "tokenizer_digest_sha256": compute_tokenizer_digest(preset["model_id"]),
        "seed": COMMON_DEFAULTS["seed"],
        "data_seed": COMMON_DEFAULTS["data_seed"],
        "train_file_sha256": sha256_file(args.train_file) if args.train_file and Path(args.train_file).exists() else None,
        "eval_file_sha256": sha256_file(args.eval_file) if args.eval_file and Path(args.eval_file).exists() else None,
        "requirements_lock_sha256": sha256_file(req_lock) if req_lock.exists() else None,
        "effective_sft_kwargs": effective_kwargs,
        **strategy_meta,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "resume_from_checkpoint": args.resume_from_checkpoint,
        "checkpoint_artifact_digest": checkpoint_digest,
        "quantization": COMMON_DEFAULTS["quantization"],
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_use_double_quant": True,
    }


def write_pending_output(output_dir: Path, manifest: dict[str, Any], preset: dict[str, Any]) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "train_run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "PENDING_REAL_TRAIN.txt").write_text(
        "실제 GPU 학습 전 상태입니다. adapter_model.safetensors 는 아직 생성되지 않았습니다.\n"
        f"model_tag={preset['model_tag']}\nmodel_id={preset['model_id']}\n",
        encoding="utf-8",
    )
    return str(manifest_path)


def evaluate_manifest_status(manifest_path: str | Path, manifest: dict[str, Any]) -> tuple[int, int]:
    manifest_present = Path(manifest_path).exists()
    manifest_complete = all([
        manifest_present,
        manifest.get("git_sha") not in (None, "UNKNOWN"),
        manifest.get("tokenizer_digest_sha256") is not None,
        manifest.get("train_file_sha256") is not None,
        manifest.get("requirements_lock_sha256") is not None,
        manifest.get("effective_sft_kwargs") is not None,
        manifest.get("start_utc") is not None,
        manifest.get("end_utc") is not None,
        manifest.get("checkpoint_artifact_digest") is not None,
    ])
    return int(manifest_present), int(manifest_complete)


def load_jsonl_as_text_dataset(path: str, tokenizer):
    from datasets import Dataset
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            prompt = str(rec.get("prompt", "")).strip()
            completion = str(rec.get("completion", "")).strip()
            if not prompt or not completion:
                continue
            try:
                messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": completion}]
                text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            except Exception:
                text = prompt + "\n" + completion
            rows.append({"text": text})
    return Dataset.from_list(rows)


def write_json(path: str | Path, obj: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def hash_directory(dir_path: Path) -> str | None:
    if not dir_path.exists():
        return None
    h = hashlib.sha256()
    for f in sorted(dir_path.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(dir_path).as_posix().encode("utf-8"))
            with f.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
    return h.hexdigest()


def run_dry_run(args: argparse.Namespace) -> None:
    preset, warnings = resolve_preset(args)
    version_warning = validate_transformers_version()
    if version_warning:
        warnings.append(version_warning)
    effective_kwargs, strategy_meta = build_effective_kwargs(args, preset)
    missing = detect_missing_packages()
    manifest = build_train_run_manifest(args, preset, effective_kwargs, strategy_meta)
    manifest_path = write_pending_output(Path(args.output_dir), manifest, preset)
    manifest_present, manifest_complete = evaluate_manifest_status(manifest_path, manifest)
    config_blockers: list[str] = []
    if not args.train_file or not Path(args.train_file).exists():
        config_blockers.append("missing_train_file")
    if args.eval_file and not Path(args.eval_file).exists():
        config_blockers.append("missing_eval_file")
    config_ready = int(len(config_blockers) == 0)
    runtime_blockers: list[str] = []
    if missing:
        runtime_blockers.append("missing_packages")
    runtime_ready = int(config_ready == 1 and len(runtime_blockers) == 0)
    result = {
        "AI20_SMALL_MODEL_DRYRUN_OK": 1,
        "SMALL_MODEL_TRAIN_OK": 0,
        "SMALL_MODEL_OUTPUT_DIR_PRESENT": 1,
        "ADAPTER_MODEL_PRESENT_OK": 0,
        "TRAIN_RUN_MANIFEST_V1_OK": 1,
        "TRAIN_RUN_MANIFEST_PRESENT_OK": manifest_present,
        "TRAIN_RUN_MANIFEST_COMPLETE_OK": manifest_complete,
        "model_id": preset["model_id"],
        "model_tag": preset["model_tag"],
        "target_vram_gb": preset["target_vram_gb"],
        "train_file": args.train_file,
        "eval_file": args.eval_file,
        "output_dir": args.output_dir,
        "dry_run": True,
        "effective_sft_kwargs": effective_kwargs,
        **strategy_meta,
        "effective_sft_kwargs_scope": "config_assuming_runtime_ready",
        "TRAINING_ARGUMENTS_STRATEGY_KEY_RESOLVED_FOR_REAL_RUN_OK": int(strategy_meta.get("training_arguments_strategy_key_resolved") is not None),
        "missing_packages": missing,
        "warnings": warnings,
        "config_ready_for_training": config_ready,
        "runtime_ready_for_training": runtime_ready,
        "config_blockers": config_blockers,
        "runtime_blockers": runtime_blockers,
        "ready_for_real_gpu_train": runtime_ready,
        "tokenizer_digest_sha256": manifest.get("tokenizer_digest_sha256"),
        "train_file_sha256": manifest.get("train_file_sha256"),
        "eval_file_sha256": manifest.get("eval_file_sha256"),
        "requirements_lock_sha256": manifest.get("requirements_lock_sha256"),
        "resume_from_checkpoint": args.resume_from_checkpoint,
        "REAL_TRAIN_GIT_SHA_RESOLVED_OK": int(manifest.get("git_sha") not in (None, "UNKNOWN")),
        "note": "GPU 환경에서 --dry-run 없이 실행하면 adapter_model.safetensors 와 실제 train_run_manifest가 생성됩니다. 실학습은 git_sha resolve 및 TrainingArguments strategy key resolve에 실패하면 fail-closed 됩니다.",
    }
    out = Path("tmp") / f"ai20_{preset['model_tag']}_dryrun_result.json"
    write_json(out, result)
    print("AI20_SMALL_MODEL_DRYRUN_OK=1")
    print("SMALL_MODEL_OUTPUT_DIR_PRESENT=1")
    print(f"TRAIN_RUN_MANIFEST_PRESENT_OK={manifest_present}")
    print(f"TRAIN_RUN_MANIFEST_COMPLETE_OK={manifest_complete}")
    print(f"READY_FOR_REAL_GPU_TRAIN={runtime_ready}")
    print(f"RESULT_JSON={out}")


def run_train(args: argparse.Namespace) -> None:
    preset, warnings = resolve_preset(args)
    if warnings:
        print("WARNING:", "; ".join(warnings), file=sys.stderr)

    if not args.train_file or not Path(args.train_file).exists():
        raise RuntimeError(f"TRAIN_FILE_NOT_FOUND:{args.train_file}")
    if args.eval_file and not Path(args.eval_file).exists():
        raise RuntimeError(f"EVAL_FILE_NOT_FOUND:{args.eval_file}")

    effective_kwargs, strategy_meta = build_effective_kwargs(args, preset)
    git_sha = get_git_sha()
    enforce_real_train_fail_closed(git_sha, strategy_meta)

    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
    from peft import LoraConfig, TaskType, get_peft_model
    from trl import SFTTrainer
    import datetime as dt
    import torch

    tokenizer = AutoTokenizer.from_pretrained(preset["model_id"], trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    bf16, fp16 = pick_precision_flags()
    compute_dtype = torch.bfloat16 if bf16 else (torch.float16 if fp16 else torch.float32)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )
    model = AutoModelForCausalLM.from_pretrained(
        preset["model_id"],
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False

    peft_config = LoraConfig(
        r=preset["lora_r"],
        lora_alpha=preset["lora_alpha"],
        lora_dropout=preset["lora_dropout"],
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=COMMON_DEFAULTS["target_modules"],
    )
    model = get_peft_model(model, peft_config)

    train_dataset = load_jsonl_as_text_dataset(args.train_file, tokenizer)
    eval_dataset = load_jsonl_as_text_dataset(args.eval_file, tokenizer) if args.eval_file else None
    training_args = TrainingArguments(**effective_kwargs)

    start_utc = dt.datetime.utcnow().isoformat() + "Z"
    pre_manifest = build_train_run_manifest(args, preset, effective_kwargs, strategy_meta, start_utc=start_utc)
    write_pending_output(Path(args.output_dir), pre_manifest, preset)
    write_json(Path("tmp") / f"ai20_{preset['model_tag']}_train_manifest_pre.json", pre_manifest)

    trainer_params = inspect.signature(SFTTrainer).parameters
    tokenizer_kwarg = "processing_class" if "processing_class" in trainer_params else "tokenizer"
    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=training_args,
        dataset_text_field="text",
        max_seq_length=preset["max_seq_length"],
        packing=False,
        **{tokenizer_kwarg: tokenizer},
    )
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    end_utc = dt.datetime.utcnow().isoformat() + "Z"
    checkpoint_digest = hash_directory(out_dir)
    final_manifest = build_train_run_manifest(args, preset, effective_kwargs, strategy_meta, start_utc=start_utc, end_utc=end_utc, checkpoint_digest=checkpoint_digest)
    final_manifest_path = out_dir / "train_run_manifest.json"
    write_json(final_manifest_path, final_manifest)
    write_json(Path("tmp") / f"ai20_{preset['model_tag']}_train_manifest.json", final_manifest)
    manifest_present, manifest_complete = evaluate_manifest_status(final_manifest_path, final_manifest)
    result = {
        "SMALL_MODEL_TRAIN_OK": 1,
        "SMALL_MODEL_OUTPUT_DIR_PRESENT": int(out_dir.exists()),
        "ADAPTER_MODEL_PRESENT_OK": int((out_dir / "adapter_model.safetensors").exists()),
        "TRAIN_RUN_MANIFEST_V1_OK": 1,
        "TRAIN_RUN_MANIFEST_PRESENT_OK": manifest_present,
        "TRAIN_RUN_MANIFEST_COMPLETE_OK": manifest_complete,
        "model_id": preset["model_id"],
        "model_tag": preset["model_tag"],
        "output_dir": args.output_dir,
        "train_samples": len(train_dataset),
        "eval_samples": len(eval_dataset) if eval_dataset is not None else 0,
        "checkpoint_artifact_digest": checkpoint_digest,
        "effective_sft_kwargs": effective_kwargs,
        **strategy_meta,
        "effective_sft_kwargs_scope": "applied_runtime_config",
        "resume_from_checkpoint": args.resume_from_checkpoint,
        "config_ready_for_training": 1,
        "runtime_ready_for_training": 1,
        "REAL_TRAIN_GIT_SHA_RESOLVED_OK": 1,
        "TRAINING_ARGUMENTS_STRATEGY_KEY_RESOLVED_FOR_REAL_RUN_OK": 1,
    }
    out = Path("tmp") / f"ai20_{preset['model_tag']}_train_result.json"
    write_json(out, result)
    print("SMALL_MODEL_TRAIN_OK=1")
    print(f"SMALL_MODEL_OUTPUT_DIR_PRESENT={int(out_dir.exists())}")
    print(f"ADAPTER_MODEL_PRESENT_OK={int((out_dir / 'adapter_model.safetensors').exists())}")
    print(f"TRAIN_RUN_MANIFEST_PRESENT_OK={manifest_present}")
    print(f"TRAIN_RUN_MANIFEST_COMPLETE_OK={manifest_complete}")
    print(f"RESULT_JSON={out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="AI-20 small deployment QLoRA trainer")
    ap.add_argument("--model-id", type=str, default=None)
    ap.add_argument("--target-tag", type=str, required=True, choices=sorted(TARGET_PRESETS.keys()))
    ap.add_argument("--train-file", type=str, default="data/synthetic_v40/train.jsonl")
    ap.add_argument("--eval-file", type=str, default="data/synthetic_v40/validation.jsonl")
    ap.add_argument("--output-dir", type=str, required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume-from-checkpoint", type=str, default=None)
    ap.add_argument("--allow-model-override", action="store_true")
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--num-train-epochs", type=float, default=None)
    ap.add_argument("--warmup-ratio", type=float, default=None)
    ap.add_argument("--eval-steps", type=int, default=None)
    ap.add_argument("--save-steps", type=int, default=None)
    ap.add_argument("--save-total-limit", type=int, default=None)
    args = ap.parse_args()
    if args.dry_run:
        run_dry_run(args)
    else:
        run_train(args)


if __name__ == "__main__":
    main()
