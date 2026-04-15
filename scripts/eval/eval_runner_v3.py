from __future__ import annotations


def build_quantization_config():
    import torch
    from transformers import BitsAndBytesConfig
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type='nf4',
        bnb_4bit_compute_dtype=torch.bfloat16,
    )


def load_real_model(model_id: str, adapter_dir: str):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    quant_cfg = build_quantization_config()
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        trust_remote_code=True,
        quantization_config=quant_cfg,
        device_map='auto',
        low_cpu_mem_usage=True,
    )
    model = PeftModel.from_pretrained(model, adapter_dir)
    model.eval()
    return model, tokenizer


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Butler eval runner v3")
    ap.add_argument("--model-id",    required=True)
    ap.add_argument("--adapter-dir", required=True)
    ap.add_argument("--report-path", default="tmp/eval_runner_report.json")
    ap.add_argument("--dry-run",     action="store_true")
    args = ap.parse_args(argv)
    if args.dry_run:
        print("EVAL_RUNNER_V3_DRYRUN_OK=1")
        return 0
    model, tokenizer = load_real_model(args.model_id, args.adapter_dir)
    print("EVAL_RUNNER_V3_LOADED_OK=1")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
