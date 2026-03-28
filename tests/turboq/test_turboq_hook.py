from __future__ import annotations

from types import SimpleNamespace

import torch

from scripts.turboq.turboq_butler_hook_v1 import ButlerTurboQuantHook


class DummyModel:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            num_hidden_layers=2,
            num_attention_heads=32,
            num_key_value_heads=8,
            head_dim=128,
        )

    def forward(self, *args, **kwargs):
        K = torch.randn(1, 8, 16, 128)
        V = torch.randn(1, 8, 16, 128)
        return {'past_key_values': ((K, V), (K.clone(), V.clone())), 'token_count': 16}


class BadShapeModel(DummyModel):
    def forward(self, *args, **kwargs):
        K = torch.randn(1, 8, 16, 64)
        V = torch.randn(1, 8, 16, 64)
        return {'past_key_values': ((K, V),), 'token_count': 16}


def test_wrapper_mode_compresses_cache_to_dict_payloads() -> None:
    model = DummyModel()
    hook = ButlerTurboQuantHook(bits=3, mode='wrapper')
    hook.apply_to_model(model)
    output = model.forward()
    assert isinstance(output['past_key_values'], tuple)
    first_layer = output['past_key_values'][0]
    assert isinstance(first_layer[0], dict)
    assert first_layer[0]['ok'] is True
    assert first_layer[0]['bits'] == 3


def test_fallback_on_unsupported_cache_shape_returns_original_path() -> None:
    model = BadShapeModel()
    hook = ButlerTurboQuantHook(bits=3, mode='wrapper')
    hook.apply_to_model(model)
    output = model.forward()
    assert isinstance(output['past_key_values'][0][0], torch.Tensor)
    stats = hook.get_memory_stats()
    assert stats['fallback_count'] >= 1
    assert stats['incompatible_request_count'] >= 1


def test_memory_stats_only_expose_targets_before_measurement() -> None:
    hook = ButlerTurboQuantHook(bits=3)
    hook._init_compressors(DummyModel())
    stats = hook.get_memory_stats()
    assert stats['compression_ratio_target'] == 16 / 3
    assert stats['measured_compression_ratio'] is None
    assert stats['model_config_snapshot']['num_heads'] == 32
