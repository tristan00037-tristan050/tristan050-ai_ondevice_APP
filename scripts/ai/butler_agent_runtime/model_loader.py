from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .runtime_contracts import DeviceProfile, LoadMeta, ModelSpec

ALLOW_LOCAL_ECHO_ENV = 'ALLOW_LOCAL_ECHO'


class LocalEchoTokenizer:
    def apply_chat_template(self, messages, tokenize=True, return_tensors='pt', add_generation_prompt=True, **kwargs):
        import torch
        text = '\n'.join(m['content'] for m in messages)
        ids = torch.tensor([[ord(c) % 255 for c in text[:64]]], dtype=torch.long)
        return ids

    def decode(self, ids, skip_special_tokens=True):
        if isinstance(ids, (list, tuple)):
            ids = ids[0]
        try:
            flat = ids.tolist()
        except Exception:
            flat = list(ids)
        return ''.join(chr((int(x) % 26) + 97) for x in flat)


class LocalEchoModel:
    def __init__(self, label: str):
        self.label = label
        self.device = 'cpu'

    def eval(self):
        return self

    def generate(self, inputs, max_new_tokens=64, temperature=0.0, do_sample=False):
        import torch
        if not hasattr(inputs, 'shape'):
            inputs = torch.tensor(inputs, dtype=torch.long)
        prefix = inputs.clone()
        suffix_seed = f'{self.label}:{int(inputs.sum().item())}:{max_new_tokens}'
        suffix = torch.tensor([[ord(c) % 255 for c in suffix_seed[: min(max_new_tokens, len(suffix_seed))]]], dtype=torch.long)
        return torch.cat([prefix, suffix], dim=1)


def probe_device() -> DeviceProfile:
    errors: list[str] = []
    ram = 0.0
    cpu_usage = 0.0
    battery_pct = None
    battery_plugged = None
    try:
        import psutil  # type: ignore
        psutil.cpu_percent(interval=None)
        cpu_usage = float(psutil.cpu_percent(interval=0.1))
        ram = round(psutil.virtual_memory().available / (1024**3), 2)
        batt = psutil.sensors_battery()
        if batt is not None:
            battery_pct = int(batt.percent)
            battery_plugged = 1 if batt.power_plugged else 0
    except Exception as e:
        errors.append(f'psutil:{type(e).__name__}')
    cpu_cores = os.cpu_count() or 0
    cuda_available = 0
    vram = 0.0
    try:
        import torch  # type: ignore
        cuda_available = 1 if torch.cuda.is_available() else 0
        if cuda_available:
            free_b, _total_b = torch.cuda.mem_get_info()
            vram = round(free_b / (1024**3), 2)
    except Exception as e:
        errors.append(f'torch:{type(e).__name__}')
    rec = 'high'
    if ram < 6 or (cuda_available and vram < 8) or cpu_usage > 80 or (battery_pct is not None and battery_pct < 20 and battery_plugged == 0):
        rec = 'light'
    return DeviceProfile(1, ram, cpu_cores, cpu_usage, battery_pct, battery_plugged, cuda_available, vram, 'normal', rec, errors)


def select_model(profile: DeviceProfile, force: str | None = None) -> dict[str, Any]:
    if force == 'light':
        return {'primary_selected': 'light', 'selected': 'light', 'reason_code': 'forced_light', 'profile_used': 1, 'fallback_used': 0, 'fallback_reason': '', 'mismatch_with_recommendation': int(profile.recommendation != 'light')}
    if force == 'high':
        return {'primary_selected': 'high', 'selected': 'high', 'reason_code': 'forced_high', 'profile_used': 1, 'fallback_used': 0, 'fallback_reason': '', 'mismatch_with_recommendation': int(profile.recommendation != 'high')}
    if profile.ram_avail_gb < 6:
        reason='ram_low'; sel='light'
    elif profile.cuda_available and profile.vram_avail_gb < 8:
        reason='vram_low'; sel='light'
    elif (profile.battery_pct is not None and profile.battery_pct < 20 and profile.battery_plugged == 0):
        reason='battery_low'; sel='light'
    elif profile.cpu_usage_pct > 80:
        reason='cpu_busy'; sel='light'
    elif profile.thermal_state in ('hot','throttled'):
        reason='thermal_hot'; sel='light'
    else:
        reason='ram_sufficient'; sel='high'
    return {'primary_selected': sel, 'selected': sel, 'reason_code': reason, 'profile_used': 1, 'fallback_used': 0, 'fallback_reason': '', 'mismatch_with_recommendation': int(profile.recommendation != sel)}


def select_model_spec(profile: DeviceProfile, high_model_path: str, light_model_path: str, adapter_path: str, force: str | None = None) -> ModelSpec:
    router = select_model(profile, force=force)
    selected = router['selected']
    if selected == 'high':
        return ModelSpec('high', high_model_path, adapter_path, '4bit', 'transformers', router['reason_code'])
    return ModelSpec('light', light_model_path, None, '4bit', 'transformers', router['reason_code'])


def _local_echo_allowed(dev_fallback: bool = False) -> bool:
    return dev_fallback or os.getenv(ALLOW_LOCAL_ECHO_ENV, '0') == '1'


def load(model_path: str, adapter_path: str | None = None, quant_mode: str = '4bit', selected: str = 'light', dev_fallback: bool = False):
    try:
        import torch  # noqa
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # type: ignore
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True, local_files_only=True)
        import torch as _torch
        quant_cfg = None
        _mps_available = hasattr(_torch.backends, 'mps') and _torch.backends.mps.is_available()
        _cuda_available = _torch.cuda.is_available()
        # MPS(Apple Silicon) 환경에서는 bitsandbytes 4bit 미지원 — float16으로 fallback
        if quant_mode == '4bit' and not _mps_available:
            quant_cfg = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type='nf4',
                bnb_4bit_compute_dtype=_torch.bfloat16,
            )
        _dtype = _torch.float16 if (_mps_available or quant_cfg is None) else None
        _device_map = 'mps' if _mps_available else 'auto'
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            trust_remote_code=True,
            quantization_config=quant_cfg,
            dtype=_dtype,
            device_map=_device_map,
            low_cpu_mem_usage=True,
            local_files_only=True,
        )
        if adapter_path:
            from peft import PeftModel  # type: ignore
            model = PeftModel.from_pretrained(model, adapter_path, local_files_only=True)
        model.eval()
        return model, tokenizer, LoadMeta(1, 'transformers', quant_mode, str(getattr(model, 'device', 'auto')), 0, '', selected, selected)
    except Exception as e:
        if not _local_echo_allowed(dev_fallback=dev_fallback):
            raise
        model = LocalEchoModel(selected)
        tokenizer = LocalEchoTokenizer()
        meta = LoadMeta(1, 'local_echo', quant_mode, 'cpu', 1 if selected == 'light' else 0, type(e).__name__, selected, selected, type(e).__name__)
        return model, tokenizer, meta


def apply_fallback(router_result: dict[str, Any], failure_reason: str) -> dict[str, Any]:
    new_res = dict(router_result)
    if new_res['primary_selected'] == 'high':
        new_res['selected'] = 'light'
        new_res['fallback_used'] = 1
        new_res['fallback_reason'] = failure_reason
    return new_res
