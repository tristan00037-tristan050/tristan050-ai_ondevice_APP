from __future__ import annotations

from butler_pc_core.cards.box3.engine_compat import check_engine_model_compatibility, detect_model_format


def test_gguf_requires_llama_cpp_or_partial():
    verdict = check_engine_model_compatibility("GGUF")
    assert verdict.required_engine == "llama_cpp"
    if not verdict.import_available:
        assert verdict.fail_class == "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE"


def test_unknown_model_format_is_partial():
    verdict = check_engine_model_compatibility("unknown")
    assert verdict.compatible is False
    assert verdict.fail_class == "PARTIAL_REAL_RUNNER_RUNTIME_UNAVAILABLE"


def test_detect_model_format():
    assert detect_model_format("butler.gguf") == "GGUF"
    assert detect_model_format("mlx_model_dir") == "MLX"
    assert detect_model_format("model.unknown") == "unknown"
