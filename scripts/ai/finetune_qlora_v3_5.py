#!/usr/bin/env python3
from __future__ import annotations
import argparse, inspect, json
from pathlib import Path

def build_sft_config_kwargs(args)->dict:
    return {"output_dir":args.output_dir,"num_train_epochs":args.num_train_epochs,"per_device_train_batch_size":args.per_device_train_batch_size,"gradient_accumulation_steps":args.gradient_accumulation_steps,"learning_rate":args.learning_rate,"logging_steps":args.logging_steps,"save_steps":args.save_steps,"save_total_limit":args.save_total_limit,"warmup_ratio":args.warmup_ratio,"gradient_checkpointing":True,"load_best_model_at_end":True,"metric_for_best_model":"eval_loss","greater_is_better":False,"max_seq_length":args.max_seq_length,"fp16":False,"bf16":False}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--model-id", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--train-file", required=True)
    ap.add_argument("--eval-file")
    ap.add_argument("--output-dir", default="artifacts/qlora_run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", default=None)
    ap.add_argument("--num-train-epochs", type=float, default=3.0)
    ap.add_argument("--per-device-train-batch-size", type=int, default=1)
    ap.add_argument("--gradient-accumulation-steps", type=int, default=8)
    ap.add_argument("--learning-rate", type=float, default=2e-4)
    ap.add_argument("--logging-steps", type=int, default=5)
    ap.add_argument("--save-steps", type=int, default=100)
    ap.add_argument("--save-total-limit", type=int, default=3)
    ap.add_argument("--eval-steps", type=int, default=50)
    ap.add_argument("--warmup-ratio", type=float, default=0.05)
    ap.add_argument("--max-seq-length", type=int, default=1024)
    args=ap.parse_args()
    if not args.dry_run:
        from datasets import load_dataset
        from peft import LoraConfig
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from trl import SFTConfig, SFTTrainer
        dataset=load_dataset("json", data_files={"train":args.train_file, **({"eval":args.eval_file} if args.eval_file else {})})
        train_dataset=dataset["train"]; eval_dataset=dataset.get("eval")
        sample=train_dataset[0]
        if "prompt" not in sample or "completion" not in sample: raise RuntimeError("TRAIN_DATA_FORMAT_INVALID:prompt_completion_required")
        bnb=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype="bfloat16")
        tokenizer=AutoTokenizer.from_pretrained(args.model_id)
        if tokenizer.pad_token is None and tokenizer.eos_token is not None: tokenizer.pad_token = tokenizer.eos_token
        model=AutoModelForCausalLM.from_pretrained(args.model_id, quantization_config=bnb, device_map="auto")
        model.config.use_cache=False
        peft_config=LoraConfig(r=16,lora_alpha=32,lora_dropout=0.05,target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],task_type="CAUSAL_LM")
        kwargs=build_sft_config_kwargs(args)
        sft_params=inspect.signature(SFTConfig).parameters
        if "eval_strategy" in sft_params: kwargs["eval_strategy"] = "steps" if eval_dataset is not None else "no"
        elif "evaluation_strategy" in sft_params: kwargs["evaluation_strategy"] = "steps" if eval_dataset is not None else "no"
        if eval_dataset is not None: kwargs["eval_steps"] = args.eval_steps
        trainer=SFTTrainer(model=model, train_dataset=train_dataset, eval_dataset=eval_dataset, processing_class=tokenizer, peft_config=peft_config, args=SFTConfig(**kwargs))
        trainer.train(resume_from_checkpoint=args.resume)
    Path("tmp").mkdir(exist_ok=True)
    Path("tmp/qlora_dryrun_result.json").write_text(json.dumps({"QLORA_SCRIPT_OK":1,"model_id":args.model_id,"train_file":args.train_file,"eval_file":args.eval_file,"output_dir":args.output_dir,"dry_run":args.dry_run,"resume":args.resume,"num_train_epochs":args.num_train_epochs,"warmup_ratio":args.warmup_ratio,"eval_steps":args.eval_steps,"save_total_limit":args.save_total_limit,"gradient_checkpointing":True,"load_best_model_at_end":True,"format":"instruction(prompt+completion)"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("QLORA_SCRIPT_OK=1")

if __name__=="__main__":
    main()
