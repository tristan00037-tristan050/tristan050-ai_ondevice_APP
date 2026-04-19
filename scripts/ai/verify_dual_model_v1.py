from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ai.device_profiler_v1 import collect_device_profile
from scripts.ai.model_router_v1 import route_model, apply_fallback


def _digest16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_quantization_config():
    import torch
    from transformers import BitsAndBytesConfig
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )


def load_model_tokenizer(model_path: str, adapter_path: str | None = None):
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    bnb_config = build_quantization_config()
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        trust_remote_code=True,
        quantization_config=bnb_config,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    if adapter_path:
        model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()
    return model, tokenizer


def _prepare_inputs(tokenizer, prompt: str):
    messages = [{"role": "user", "content": prompt}]
    return tokenizer.apply_chat_template(messages, tokenize=True, return_tensors="pt", add_generation_prompt=True)


def _real_output(model, tokenizer, prompt: str) -> str:
    import torch
    inputs = _prepare_inputs(tokenizer, prompt)
    if hasattr(model, "device"):
        inputs = inputs.to(model.device)
    with torch.no_grad():
        out = model.generate(inputs, max_new_tokens=64, do_sample=False, temperature=0.0)
    return tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True).strip()


def _validate_output_shape(text: str) -> bool:
    return isinstance(text, str) and len(text.strip()) >= 5


def _run_real_load_generate(model_path: str, adapter_path: str | None = None) -> tuple[bool, str, str]:
    try:
        model, tokenizer = load_model_tokenizer(model_path, adapter_path=adapter_path)
        text = _real_output(model, tokenizer, "오늘 회의 내용을 짧게 정리해 주세요.")
        return True, text, "ok"
    except Exception as e:
        return False, "", f"load_or_generate_failed:{type(e).__name__}"


def verify_dual_model(high_model_path: str, light_model_path: str, adapter_path: str,
                      dry_run: bool = False, force_light: bool = False,
                      force_high: bool = False, force_high_load_fail: bool = False) -> dict[str, Any]:
    profile = collect_device_profile()
    router = route_model(profile, force="light" if force_light else ("high" if force_high else None))

    checks = {f"V0{i}": 0 for i in range(1, 9)}
    fail_codes: list[str] = []
    evidence: dict[str, str] = {"high_output_digest16": "", "light_output_digest16": ""}

    checks["V01"] = 1 if profile.get("ok") == 1 else 0
    checks["V02"] = 1 if router.get("ok") == 1 else 0
    checks["V03"] = 1 if router.get("reason_code") else 0

    if dry_run:
        high_ok, high_text, high_reason = True, "[dry-run: high model not loaded]", "ok"
        light_ok, light_text, light_reason = True, "[dry-run: light model not loaded]", "ok"
    else:
        high_ok, high_text, high_reason = _run_real_load_generate(high_model_path, adapter_path=None if force_high_load_fail else adapter_path)
        router = apply_fallback(router, high_model_load_ok=high_ok)
        light_ok, light_text, light_reason = _run_real_load_generate(light_model_path, adapter_path=None)

    # V04/V06: router가 light를 primary로 선택한 경우 high 로드는 optional
    # 저사양 기기에서 light가 정상 선택됐을 때 high 실패로 ok=0이 되는 문제 수정
    light_is_primary = router.get("selected") == "light" and router.get("primary_selected") == "light"
    checks["V04"] = 1 if (high_ok or router.get("fallback_used") or light_is_primary) else 0
    checks["V05"] = 1 if light_ok else 0
    checks["V06"] = 1 if ((high_ok and _validate_output_shape(high_text)) or router.get("fallback_used") or light_is_primary) else 0
    checks["V07"] = 1 if (light_ok and _validate_output_shape(light_text)) else 0
    checks["V08"] = 1 if ((force_light and router["primary_selected"] == "light") or (force_high and router["primary_selected"] == "high") or (not force_light and not force_high)) else 0

    if not high_ok and not router.get("fallback_used"):
        fail_codes.append(high_reason)
    if not light_ok:
        fail_codes.append(light_reason)

    evidence["high_output_digest16"] = _digest16(high_text) if high_text else ""
    evidence["light_output_digest16"] = _digest16(light_text) if light_text else ""

    pass_count = sum(checks.values())
    result = {
        "execution_mode": "dry_run" if dry_run else "real",
        "high_model_path": high_model_path,
        "light_model_path": light_model_path,
        "adapter_path": adapter_path,
        "device_profile": profile,
        "router_result": router,
        "checks": checks,
        "pass_count": pass_count,
        "ok": 1 if pass_count == 8 else 0,
        "fail_codes": fail_codes,
        "evidence": evidence,
    }
    return result


def print_verify_result(result: dict[str, Any]) -> None:
    for i in range(1, 9):
        print(f"DUAL_MODEL_VERIFY_V0{i}={result['checks'][f'V0{i}']}")
    print(f"DUAL_MODEL_VERIFY_PASS={result['pass_count']}/8")
    print(f"DUAL_MODEL_VERIFY_OK={result['ok']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--high-model-path", required=True)
    ap.add_argument("--light-model-path", required=True)
    ap.add_argument("--adapter-path", required=True)
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--force-light", action="store_true")
    grp.add_argument("--force-high", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json-out", default="tmp/dual_model_result.json")
    args = ap.parse_args(argv)

    result = verify_dual_model(
        high_model_path=args.high_model_path,
        light_model_path=args.light_model_path,
        adapter_path=args.adapter_path,
        dry_run=args.dry_run,
        force_light=args.force_light,
        force_high=args.force_high,
    )
    Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print_verify_result(result)
    return 0 if result["ok"] == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
