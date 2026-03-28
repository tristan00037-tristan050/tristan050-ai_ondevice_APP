from __future__ import annotations

from collections import Counter
from typing import Any

import torch

from .turboq_core_v1 import TurboQuantKVCache


OFFICIAL_QWEN3_4B_CONFIG = {
    'num_layers': 36,
    'num_heads': 32,
    'num_kv_heads': 8,
    'head_dim': 128,
}


class ButlerTurboQuantHook:
    def __init__(self, bits: int = 3, mode: str = 'wrapper', qjl_n_bits: int = 2048):
        if mode not in {'wrapper', 'replace'}:
            raise ValueError("mode must be 'wrapper' or 'replace'")
        self.bits = int(bits)
        self.mode = mode
        self.qjl_n_bits = int(qjl_n_bits)
        self.fallback_count = 0
        self.incompatible_request_count = 0
        self.fallback_reasons: Counter[str] = Counter()
        self.cache_compressors: dict[int, TurboQuantKVCache] = {}
        self.model_config_snapshot = dict(OFFICIAL_QWEN3_4B_CONFIG)

    def _resolve_model_config(self, model: Any) -> dict[str, int]:
        cfg = dict(OFFICIAL_QWEN3_4B_CONFIG)
        config = getattr(model, 'config', None)
        if config is None:
            return cfg
        cfg['num_layers'] = int(getattr(config, 'num_hidden_layers', cfg['num_layers']))
        cfg['num_heads'] = int(getattr(config, 'num_attention_heads', cfg['num_heads']))
        cfg['num_kv_heads'] = int(getattr(config, 'num_key_value_heads', cfg['num_kv_heads']))
        cfg['head_dim'] = int(getattr(config, 'head_dim', cfg['head_dim']))
        return cfg

    def _init_compressors(self, model: Any | None = None) -> None:
        cfg = self._resolve_model_config(model) if model is not None else dict(OFFICIAL_QWEN3_4B_CONFIG)
        self.model_config_snapshot = cfg
        self.cache_compressors = {
            layer_idx: TurboQuantKVCache(head_dim=cfg['head_dim'], bits=self.bits, qjl_n_bits=self.qjl_n_bits)
            for layer_idx in range(cfg['num_layers'])
        }

    def apply_to_model(self, model: Any) -> None:
        self._init_compressors(model)
        if self.mode == 'wrapper':
            self._apply_wrapper(model)
        else:
            self._apply_replace(model)
        setattr(model, '_butler_turboq_hook', self)

    def _apply_wrapper(self, model: Any) -> None:
        original_forward = model.forward
        hook = self
        if getattr(model, '_turboq_wrapper_applied', False):
            return

        def wrapped_forward(*args, **kwargs):
            output = original_forward(*args, **kwargs)
            return hook._wrap_model_output(output)

        model._turboq_original_forward = original_forward
        model.forward = wrapped_forward
        model._turboq_wrapper_applied = True

    def _apply_replace(self, model: Any) -> None:
        # Direct replacement is intentionally conservative and reuses the same
        # wrapper path for now. This preserves a single fail-closed code path.
        self._apply_wrapper(model)

    def _wrap_model_output(self, output: Any) -> Any:
        if output is None:
            return output
        if isinstance(output, dict):
            pkv = output.get('past_key_values')
            if pkv is not None:
                output = dict(output)
                output['past_key_values'] = self._compress_cache_safe(pkv)
            return output
        if hasattr(output, 'past_key_values'):
            pkv = getattr(output, 'past_key_values')
            if pkv is not None:
                try:
                    setattr(output, 'past_key_values', self._compress_cache_safe(pkv))
                    return output
                except Exception:
                    self._register_fallback('runtime_error')
                    return output
        if isinstance(output, tuple) and len(output) >= 2:
            try:
                output_list = list(output)
                output_list[1] = self._compress_cache_safe(output_list[1])
                return tuple(output_list)
            except Exception:
                self._register_fallback('runtime_error')
        return output

    def _register_fallback(self, reason_code: str) -> None:
        self.fallback_count += 1
        self.fallback_reasons[reason_code] += 1
        if reason_code == 'unsupported_cache_shape':
            self.incompatible_request_count += 1

    def _compress_cache_safe(self, past_key_values: Any):
        if not self.cache_compressors:
            self._register_fallback('compressor_missing')
            return past_key_values
        try:
            return self._compress_cache(past_key_values)
        except ValueError:
            self._register_fallback('unsupported_cache_shape')
            return past_key_values
        except Exception:
            self._register_fallback('runtime_error')
            return past_key_values

    def _compress_cache(self, past_key_values: Any):
        if not isinstance(past_key_values, (tuple, list)):
            raise ValueError('past_key_values must be tuple/list')
        compressed: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for layer_idx, layer_cache in enumerate(past_key_values):
            if not isinstance(layer_cache, (tuple, list)) or len(layer_cache) != 2:
                raise ValueError('each layer cache must be (K, V)')
            K, V = layer_cache
            if not isinstance(K, torch.Tensor) or not isinstance(V, torch.Tensor):
                raise ValueError('cache items must be tensors')
            if K.shape[-1] != self.model_config_snapshot['head_dim'] or V.shape[-1] != self.model_config_snapshot['head_dim']:
                raise ValueError('unsupported cache head_dim')
            compressor = self.cache_compressors.get(layer_idx)
            if compressor is None:
                self._register_fallback('compressor_missing')
                compressed.append((K, V))
                continue
            K_comp = compressor.compress_keys(K)
            V_comp = compressor.compress_values(V)
            if not K_comp.get('ok') or not V_comp.get('ok'):
                self._register_fallback(K_comp.get('reason_code') or V_comp.get('reason_code') or 'runtime_error')
                compressed.append((K, V))
                continue
            compressed.append((K_comp, V_comp))
        return tuple(compressed)

    def get_memory_stats(self) -> dict[str, Any]:
        return {
            'bits_before': 16,
            'bits_after': self.bits,
            'compression_ratio_target': 16.0 / float(self.bits),
            'fallback_count': self.fallback_count,
            'fallback_reasons': dict(self.fallback_reasons),
            'incompatible_request_count': self.incompatible_request_count,
            'model_config_snapshot': self.model_config_snapshot,
            'measured_compression_ratio': None,
            'measured_memory_reduction': None,
        }
