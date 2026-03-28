from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

try:
    import torch
except Exception:  # pragma: no cover
    torch = None


QWEN3_4B_CONFIG = {
    'num_hidden_layers': 36,
    'num_attention_heads': 32,
    'num_key_value_heads': 8,
    'head_dim': 128,
}

BASE_MODEL_MAP = {
    'butler-small': 'Qwen/Qwen3-4B',
    'butler-micro': 'Qwen/Qwen2.5-1.5B-Instruct',
    'butler-v1': 'Qwen/Qwen2.5-7B-Instruct',
}

MODEL_PATHS = {
    'butler-small': 'output/butler_model_small_v1',
    'butler-micro': 'output/butler_model_micro_v1',
    'butler-v1': 'output/butler_model_v1',
}

STUB_RESPONSES = {
    'butler-small': '[butler-small stub] 모델이 아직 로드되지 않았습니다.',
    'butler-micro': '[butler-micro stub] 모델이 아직 로드되지 않았습니다.',
    'butler-v1': '[butler-v1 stub] 모델이 아직 로드되지 않았습니다.',
}

QWEN3_MODELS = {'butler-small'}


@dataclass(slots=True)
class LoadState:
    loaded: bool = False
    load_attempted: bool = False
    stub_reason: Optional[str] = None
    fatal_error: Optional[str] = None

    @property
    def state(self) -> str:
        if self.loaded:
            return 'ready'
        if self.fatal_error:
            return 'error'
        if self.stub_reason:
            return 'stub'
        return 'uninitialized'


class ButlerModel:
    def __init__(self, model_id: str, adapter_path: str):
        self.model_id = model_id
        self.adapter_path = Path(adapter_path)
        self.model = None
        self.tokenizer = None
        self.state = LoadState()

    @property
    def is_qwen3(self) -> bool:
        return self.model_id in QWEN3_MODELS

    def ensure_loaded(self) -> bool:
        if self.state.loaded or self.state.load_attempted:
            return self.state.loaded

        self.state.load_attempted = True
        adapter_file = self.adapter_path / 'adapter_model.safetensors'
        if not adapter_file.exists():
            self.state.stub_reason = f'어댑터 없음: {adapter_file}'
            return False

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel
        except Exception as exc:
            self.state.fatal_error = f'필수 패키지 로드 실패: {exc}'
            return False

        try:
            base_id = BASE_MODEL_MAP[self.model_id]
            self.tokenizer = AutoTokenizer.from_pretrained(base_id)
            if self.is_qwen3:
                self._validate_qwen3_template()
            dtype = getattr(torch, 'bfloat16', None) if torch is not None else None
            model_kwargs = {'device_map': 'auto'}
            if dtype is not None:
                model_kwargs['torch_dtype'] = dtype
            base = AutoModelForCausalLM.from_pretrained(base_id, **model_kwargs)
            self.model = PeftModel.from_pretrained(base, str(self.adapter_path))
            self.state.loaded = True
            self.state.stub_reason = None
            return True
        except Exception as exc:
            self.state.fatal_error = str(exc)
            return False

    def _validate_qwen3_template(self) -> None:
        if self.tokenizer is None:
            raise RuntimeError('tokenizer_not_initialized')
        try:
            self.tokenizer.apply_chat_template(
                [{'role': 'user', 'content': 'ping'}],
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        except Exception as exc:
            raise RuntimeError(f'Qwen3 chat_template mismatch: {exc}') from exc

    def get_stub_response(self) -> str:
        return STUB_RESPONSES[self.model_id]

    def can_stub(self) -> bool:
        return bool(self.state.stub_reason) and not self.state.fatal_error

    def should_fail_closed(self) -> bool:
        return bool(self.state.fatal_error) and not self.state.loaded

    def build_prompt(self, messages: list[dict]) -> str:
        if self.tokenizer is None:
            raise RuntimeError('tokenizer_not_loaded')
        template_kwargs = {'enable_thinking': False} if self.is_qwen3 else {}
        return self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            **template_kwargs,
        )

    def generate(self, messages: list[dict], max_tokens: int = 512, temperature: float = 0.7) -> str:
        if self.state.loaded:
            if self.tokenizer is None or self.model is None:
                raise RuntimeError('model_not_initialized')
            prompt = self.build_prompt(messages)
            tokenized = self.tokenizer(prompt, return_tensors='pt', add_special_tokens=False)
            if hasattr(tokenized, 'to') and torch is not None and getattr(torch, 'cuda', None) and torch.cuda.is_available():
                tokenized = tokenized.to('cuda')
            gen_kwargs = {
                **tokenized,
                'max_new_tokens': max_tokens,
                'do_sample': temperature > 0,
            }
            if temperature > 0:
                gen_kwargs['temperature'] = temperature
            if self.is_qwen3:
                gen_kwargs['enable_thinking'] = False
            outputs = self.model.generate(**gen_kwargs)
            prompt_length = tokenized['input_ids'].shape[1]
            generated = outputs[0][prompt_length:]
            return self.tokenizer.decode(generated, skip_special_tokens=True)

        if self.can_stub():
            return self.get_stub_response()
        raise RuntimeError(self.state.fatal_error or 'model_not_ready')

    def readiness_dict(self) -> dict:
        return {
            'state': self.state.state,
            'loaded': self.state.loaded,
            'stub_reason': self.state.stub_reason,
            'error': self.state.fatal_error,
            'base_model': BASE_MODEL_MAP[self.model_id],
            'adapter_path': str(self.adapter_path),
        }


class ModelPool:
    def __init__(self):
        self._pool: Dict[str, ButlerModel] = {
            model_id: ButlerModel(model_id, adapter_path)
            for model_id, adapter_path in MODEL_PATHS.items()
        }

    def get_model(self, model_id: str) -> Optional[ButlerModel]:
        model = self._pool.get(model_id)
        if model is None:
            return None
        model.ensure_loaded()
        return model


    def probe_all(self) -> None:
        for model in self._pool.values():
            model.ensure_loaded()

    def loaded_count(self) -> int:
        return sum(1 for model in self._pool.values() if model.state.loaded)

    def stub_count(self) -> int:
        return sum(1 for model in self._pool.values() if model.can_stub())

    def fatal_count(self) -> int:
        return sum(1 for model in self._pool.values() if model.should_fail_closed())

    def readiness_report(self) -> dict:
        return {model_id: model.readiness_dict() for model_id, model in self._pool.items()}

    def model_ids(self) -> list[str]:
        return list(self._pool.keys())


model_pool = ModelPool()
