from __future__ import annotations

MOBILE_CONFIG = {
    'android': {
        'bits': 3,
        'max_seq_len_target': 4096,
        'without_turboq_limit': 512,
        'target_ram_mb': 2048,
    },
    'ios': {
        'bits': 3,
        'max_seq_len_target': 4096,
        'without_turboq_limit': 512,
        'target_ram_mb': 2048,
    },
}


class MobileTurboQuantConfig:
    @staticmethod
    def get_optimal_bits(available_ram_gb: float) -> dict:
        """Heuristic only. Real-device validation is still required."""
        if available_ram_gb >= 8:
            bits = 4
        elif available_ram_gb >= 6:
            bits = 3
        else:
            bits = 2
        return {
            'bits': bits,
            'note': 'heuristic_value_needs_real_device_validation',
            'measured_max_seq_len': None,
            'measured_thermal_status': None,
        }

    @staticmethod
    def get_mnn_integration_plan() -> dict:
        return {
            'scope': 'plan_only_real_execution_is_execution_team_scope',
            'step1': 'LoRA merge_and_unload() or full-weight export preparation',
            'step2': 'Export torch model through llmexport / ONNX path',
            'step3': 'Insert TurboQuant KV cache wrapper at runtime cache boundary',
            'step4': 'Convert and package for MNN runtime',
            'step5': 'Validate Android APK / iOS framework with llm_demo-compatible config',
            'mnn_cmake_flags': [
                '-DMNN_LOW_MEMORY=true',
                '-DMNN_CPU_WEIGHT_DEQUANT_GEMM=true',
                '-DMNN_BUILD_LLM=true',
                '-DMNN_SUPPORT_TRANSFORMER_FUSE=true',
            ],
            'llm_demo_call': './llm_demo /path/to/Qwen3-4B-MNN/config.json prompt.txt',
            'conversion_note': 'TurboQuant cache insertion is a Butler-side runtime plan; no fake ONNX/MNN artifact is produced in this bundle.',
            'measured_latency_ms': None,
            'measured_memory_mb': None,
        }
