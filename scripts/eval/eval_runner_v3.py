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
