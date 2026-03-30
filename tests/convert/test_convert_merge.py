from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

from scripts.convert import StructureOrInputError
from scripts.convert.convert_merge_v1 import merge, sha256_file


def test_sha256_file(tmp_path: Path):
    path = tmp_path / "a.bin"
    path.write_bytes(b"abc")
    assert sha256_file(path) == hashlib.sha256(b"abc").hexdigest()[:16]


def test_merge_missing_adapter_raises(tmp_path: Path):
    with pytest.raises(StructureOrInputError):
        merge(str(tmp_path), str(tmp_path / "out"))


def test_merge_success_with_fake_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"adapter-weights")
    (adapter_dir / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "fake/base"}),
        encoding="utf-8",
    )

    class FakeTokenizer:
        def save_pretrained(self, output_dir: str):
            Path(output_dir, "tokenizer.json").write_text("{}", encoding="utf-8")
            Path(output_dir, "tokenizer_config.json").write_text("{}", encoding="utf-8")

    class FakeMerged:
        def save_pretrained(self, output_dir: str):
            Path(output_dir, "model.safetensors").write_bytes(b"merged")

    class FakePeftLoaded:
        def merge_and_unload(self):
            return FakeMerged()

    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoTokenizer = types.SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: FakeTokenizer()
    )
    fake_transformers.AutoModelForCausalLM = types.SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: object()
    )

    fake_peft = types.ModuleType("peft")
    fake_peft.PeftModel = types.SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: FakePeftLoaded()
    )

    fake_torch = types.ModuleType("torch")
    fake_torch.bfloat16 = "bf16"

    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "peft", fake_peft)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    output_dir = tmp_path / "out"
    result = merge(str(adapter_dir), str(output_dir))
    assert result["base_model_id"] == "fake/base"
    assert (output_dir / "tokenizer.json").exists()
    assert (output_dir / "model.safetensors").exists()
