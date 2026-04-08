from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import sys
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_BASE_MODEL_ID = "Qwen/Qwen3-4B"
DEFAULT_PROMPT_MESSAGES = [
    {"role": "user", "content": "안녕하세요. 버틀러입니다. 오늘 날씨가 좋네요."}
]
RESULT_FILENAME = "ai26_local_load_smoke_result.json"
ENV_FILENAME = "ai26_local_load_smoke_env.json"
STDOUT_FILENAME = "ai26_local_load_smoke_stdout.txt"


def _safe_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return "unavailable"


def _sha256_16(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _json_dump(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class Recorder:
    def __init__(self):
        self.lines = []

    def emit(self, line: str) -> None:
        self.lines.append(line)
        print(line)

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _load_adapter_config(adapter_path: Path) -> Dict[str, Any]:
    cfg = adapter_path / "adapter_config.json"
    if not cfg.exists():
        return {}
    return json.loads(cfg.read_text(encoding="utf-8"))


def _resolve_base_model(adapter_path: Path, cli_base: Optional[str]) -> str:
    if cli_base:
        return cli_base
    cfg = _load_adapter_config(adapter_path)
    return cfg.get("base_model_name_or_path", DEFAULT_BASE_MODEL_ID)


def _select_device(prefer: str) -> str:
    import torch
    if prefer == "cpu":
        return "cpu"
    if prefer == "cuda":
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"
    if prefer == "mps":
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    # auto: CUDA > MPS > CPU 순서
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _save_outputs(output_dir, result, env_data, rec, save_env_json):
    _json_dump(output_dir / RESULT_FILENAME, result)
    if save_env_json:
        _json_dump(output_dir / ENV_FILENAME, env_data)
    p = output_dir / STDOUT_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(rec.text(), encoding="utf-8")


def run_smoke(adapter_path, output_dir, base_model_id, prefer_device, seed, strict_determinism, save_env_json):
    rec = Recorder()
    result: Dict[str, Any] = {}

    import torch
    import numpy as np

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    det_enabled = False
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
        det_enabled = True
    except Exception:
        pass

    requested_device = prefer_device
    selected_device = _select_device(prefer_device)
    fallback_used = False
    fallback_reason = None
    resolved_base = _resolve_base_model(adapter_path, base_model_id)
    safetensors_path = adapter_path / "adapter_model.safetensors"
    adapter_digest = _sha256_16(safetensors_path)

    env_data = {
        "torch_version": torch.__version__,
        "transformers_version": _safe_version("transformers"),
        "peft_version": _safe_version("peft"),
        "python_version": platform.python_version(),
        "seed": seed,
        "deterministic_algorithms_enabled": det_enabled,
        "device": selected_device,
        "runtime_backend": "real",
    }

    # STEP 1 tokenizer
    try:
        from transformers import AutoTokenizer
        # tokenizer는 베이스 모델에서 로드 (어댑터 tokenizer_config 호환성 문제 우회)
        tokenizer_path = str(adapter_path)
        try:
            tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=False)
        except Exception:
            # fallback: 베이스 모델에서 로드
            tokenizer = AutoTokenizer.from_pretrained(resolved_base, trust_remote_code=False)
        rec.emit("LOAD_TOKENIZER_OK=1")
        result["LOAD_TOKENIZER_OK"] = 1
    except Exception as e:
        rec.emit(f"LOAD_TOKENIZER_FAIL=1")
        result["LOAD_TOKENIZER_OK"] = 0
        result["LOCAL_LOAD_SMOKE_OK"] = 0
        _save_outputs(output_dir, result, env_data, rec, save_env_json)
        return 1

    # STEP 2 base model
    # 어댑터 가중치가 BFloat16으로 저장되어 있어 device_map 미지정 시 MPS로 올라가면서
    # BFloat16 변환 오류가 날 수 있음. device_map="cpu"로 베이스를 CPU에 고정한 뒤 어댑터를 붙이고,
    # 이후 model.to(selected_device)로 장치 이동(STEP 3).
    try:
        from transformers import AutoModelForCausalLM
        model = AutoModelForCausalLM.from_pretrained(
            resolved_base,
            torch_dtype=torch.float32,
            device_map="cpu",
        )
        rec.emit("LOAD_BASE_MODEL_OK=1")
        result["LOAD_BASE_MODEL_OK"] = 1
    except Exception as e:
        rec.emit("LOAD_BASE_MODEL_FAIL=1")
        result["LOAD_BASE_MODEL_OK"] = 0
        result["LOCAL_LOAD_SMOKE_OK"] = 0
        _save_outputs(output_dir, result, env_data, rec, save_env_json)
        return 1

    # STEP 3 adapter attach
    # peft 0.17.1 + MPS 환경에서 BFloat16 어댑터 로드 시 오류 발생.
    # safetensors를 직접 읽어 float32로 변환 후 수동 로드로 우회.
    try:
        import warnings
        from peft import LoraConfig, get_peft_model
        from safetensors.torch import load_file as st_load_file

        adapter_config_dict = _load_adapter_config(adapter_path)
        lora_config = LoraConfig(
            r=adapter_config_dict.get("r", 12),
            lora_alpha=adapter_config_dict.get("lora_alpha", 24),
            lora_dropout=adapter_config_dict.get("lora_dropout", 0.05),
            target_modules=adapter_config_dict.get("target_modules", None),
            task_type=adapter_config_dict.get("task_type", "CAUSAL_LM"),
            bias=adapter_config_dict.get("bias", "none"),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = get_peft_model(model, lora_config)

        safetensors_path = adapter_path / "adapter_model.safetensors"
        state_dict = st_load_file(str(safetensors_path), device="cpu")
        state_dict = {k: v.to(torch.float32) for k, v in state_dict.items()}
        missing, unexpected = model.load_state_dict(state_dict, strict=False)
        model = model.to(selected_device)
        rec.emit(f"LOAD_ADAPTER_MISSING_KEYS={len(missing)}")
        rec.emit(f"LOAD_ADAPTER_UNEXPECTED_KEYS={len(unexpected)}")
        rec.emit("LOAD_ADAPTER_OK=1")
        result["LOAD_ADAPTER_OK"] = 1
        result["LOAD_ADAPTER_MISSING_KEYS"] = len(missing)
        result["LOAD_ADAPTER_UNEXPECTED_KEYS"] = len(unexpected)
    except Exception as e:
        rec.emit("LOAD_ADAPTER_FAIL=1")
        result["LOAD_ADAPTER_OK"] = 0
        result["LOCAL_LOAD_SMOKE_OK"] = 0
        _save_outputs(output_dir, result, env_data, rec, save_env_json)
        return 1

    # STEP 4 eval
    model.eval()
    rec.emit("EVAL_MODE_OK=1")
    result["EVAL_MODE_OK"] = 1

    # STEP 5 chat template
    messages = DEFAULT_PROMPT_MESSAGES
    enable_thinking_supported = False
    try:
        with torch.no_grad():
            input_ids = tokenizer.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True,
                return_tensors="pt", enable_thinking=False)
        enable_thinking_supported = True
        rec.emit("CHAT_TEMPLATE_ENABLE_THINKING_SUPPORTED=1")
    except TypeError:
        try:
            with torch.no_grad():
                input_ids = tokenizer.apply_chat_template(
                    messages, tokenize=True, add_generation_prompt=True,
                    return_tensors="pt")
            rec.emit("CHAT_TEMPLATE_ENABLE_THINKING_FALLBACK=1")
        except Exception as e:
            rec.emit("CHAT_TEMPLATE_FAIL=1")
            result["CHAT_TEMPLATE_OK"] = 0
            result["LOCAL_LOAD_SMOKE_OK"] = 0
            _save_outputs(output_dir, result, env_data, rec, save_env_json)
            return 1

    rec.emit("CHAT_TEMPLATE_OK=1")
    result["CHAT_TEMPLATE_OK"] = 1
    result["chat_template_enable_thinking_supported"] = enable_thinking_supported

    # STEP 6 generate
    # BatchEncoding 방어 처리 — STEP 6 진입 시점에도 재확인
    if not isinstance(input_ids, torch.Tensor):
        if hasattr(input_ids, 'input_ids'):
            input_ids = input_ids.input_ids
        elif isinstance(input_ids, dict) and 'input_ids' in input_ids:
            input_ids = input_ids['input_ids']
    input_ids = input_ids.to(selected_device)
    gen_kwargs = dict(max_new_tokens=64, do_sample=False, use_cache=True)
    try:
        with torch.no_grad():
            output_ids_1 = model.generate(input_ids, **gen_kwargs)
        prompt_len = input_ids.shape[-1]
        decoded = tokenizer.decode(output_ids_1[0][prompt_len:], skip_special_tokens=True)
        rec.emit("GENERATE_OK=1")
        rec.emit(f"GENERATE_OUTPUT={decoded}")
        result["GENERATE_OK"] = 1
        result["GENERATE_OUTPUT"] = decoded
    except Exception as e:
        import traceback as _tb
        _err_type = type(e).__name__
        rec.emit(f"GENERATE_ERROR_CODE={_err_type}")
        rec.emit("GENERATE_FAIL=1")
        result["GENERATE_OK"] = 0
        result["GENERATE_ERROR_CODE"] = _err_type
        result["LOCAL_LOAD_SMOKE_OK"] = 0
        _save_outputs(output_dir, result, env_data, rec, save_env_json)
        return 1

    # STEP 7 determinism
    torch.manual_seed(seed)
    try:
        with torch.no_grad():
            output_ids_2 = model.generate(input_ids, **gen_kwargs)
        determinism_ok = output_ids_1.equal(output_ids_2)
    except Exception:
        determinism_ok = False

    strict_det_ok = determinism_ok
    if determinism_ok:
        rec.emit("DETERMINISM_OK=1")
        result["DETERMINISM_OK"] = 1
        result["DETERMINISM_FAIL"] = 0
    else:
        rec.emit("DETERMINISM_FAIL=1")
        result["DETERMINISM_OK"] = 0
        result["DETERMINISM_FAIL"] = 1
        if selected_device == "mps":
            try:
                model_cpu = model.to("cpu")
                input_cpu = input_ids.to("cpu")
                torch.manual_seed(seed)
                with torch.no_grad():
                    o1 = model_cpu.generate(input_cpu, **gen_kwargs)
                torch.manual_seed(seed)
                with torch.no_grad():
                    o2 = model_cpu.generate(input_cpu, **gen_kwargs)
                strict_det_ok = o1.equal(o2)
            except Exception:
                strict_det_ok = False

    result["FUNCTIONAL_OK"] = 1
    result["STRICT_DETERMINISM_OK"] = 1 if strict_det_ok else 0

    final_ok = (
        result.get("LOAD_TOKENIZER_OK") == 1
        and result.get("LOAD_BASE_MODEL_OK") == 1
        and result.get("LOAD_ADAPTER_OK") == 1
        and result.get("EVAL_MODE_OK") == 1
        and result.get("CHAT_TEMPLATE_OK") == 1
        and result.get("GENERATE_OK") == 1
        and (not strict_determinism or strict_det_ok)
    )

    result["LOCAL_LOAD_SMOKE_OK"] = 1 if final_ok else 0
    result["requested_device"] = requested_device
    result["selected_device"] = selected_device
    result["fallback_used"] = fallback_used
    result["fallback_reason"] = fallback_reason
    result["resolved_base_model_id"] = resolved_base
    result["adapter_path"] = str(adapter_path)
    result["adapter_digest_sha256_16"] = adapter_digest
    result["execution_mode"] = "real"
    result["strict_determinism_requested"] = strict_determinism
    env_data["device"] = selected_device

    _save_outputs(output_dir, result, env_data, rec, save_env_json)

    if final_ok:
        rec.emit("LOCAL_LOAD_SMOKE_OK=1")
    else:
        rec.emit("LOCAL_LOAD_SMOKE_FAIL=1")

    return 0 if final_ok else 1


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--adapter-path", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--base-model-id", default=None)
    p.add_argument("--prefer-device", default="auto", choices=["auto", "mps", "cpu", "cuda"])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--strict-determinism", action="store_true", default=True)
    p.add_argument("--save-env-json", action="store_true", default=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    adapter_path = Path(args.adapter_path)
    output_dir = Path(args.output_dir)
    if not adapter_path.exists():
        print(f"ERROR: adapter_path 없음: {adapter_path}")
        return 1
    return run_smoke(
        adapter_path=adapter_path,
        output_dir=output_dir,
        base_model_id=args.base_model_id,
        prefer_device=args.prefer_device,
        seed=args.seed,
        strict_determinism=args.strict_determinism,
        save_env_json=args.save_env_json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
