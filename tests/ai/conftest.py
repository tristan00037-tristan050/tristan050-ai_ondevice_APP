from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _ensure_compare_ft_adapter_fixture():
    """Fixture drift: tests/ai/test_compare_base_vs_ft_v1.py runs
    scripts/ai/compare_base_vs_ft_v1.py --dry-run, which reads
    tmp/test_adapter/{adapter_config.json, adapter_model.safetensors}. That
    adapter directory was never committed, so --dry-run raised FileNotFoundError
    (exit 1) and the result JSON was never written. Generate a minimal adapter
    here. The dry-run only reads adapter_config.json (.get('r')) and sha-hashes
    the .safetensors bytes (no tensor loading / no torch), so this is sufficient
    and does not exercise the real (torch-only) path.
    """
    adapter = _ROOT / "tmp" / "test_adapter"
    adapter.mkdir(parents=True, exist_ok=True)

    cfg = adapter / "adapter_config.json"
    if not cfg.exists():
        cfg.write_text(
            json.dumps(
                {
                    "peft_type": "LORA",
                    "r": 8,
                    "lora_alpha": 16,
                    "lora_dropout": 0.0,
                    "target_modules": ["q_proj", "v_proj"],
                    "task_type": "CAUSAL_LM",
                    "base_model_name_or_path": "Qwen/Qwen3-4B",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    weights = adapter / "adapter_model.safetensors"
    if not weights.exists():
        # Minimal safetensors container (empty tensor set). Only its bytes are
        # sha-hashed by --dry-run; no safetensors/torch parsing occurs.
        header = b'{"__metadata__":{"format":"pt"}}'
        weights.write_bytes(struct.pack("<Q", len(header)) + header)

    yield
