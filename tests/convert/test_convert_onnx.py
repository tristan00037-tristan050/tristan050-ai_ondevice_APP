from __future__ import annotations

import inspect
import sys
import types
from pathlib import Path

import pytest

from scripts.convert import StructureOrInputError
from scripts.convert.convert_onnx_v2 import convert_to_onnx
from scripts.convert.convert_verify_onnx_v2 import verify_onnx


def test_convert_to_onnx_missing_model_dir_raises(tmp_path: Path):
    with pytest.raises(StructureOrInputError):
        convert_to_onnx(str(tmp_path / "missing"), str(tmp_path / "a.onnx"))


def test_convert_to_onnx_fallback_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    model_dir = tmp_path / "model"
    model_dir.mkdir()

    class FakeModel:
        def eval(self):
            return None

    class FakeTokenizer:
        def __call__(self, text: str, return_tensors: str = "pt"):
            return {"input_ids": [[1, 2, 3]], "attention_mask": [[1, 1, 1]]}

    calls = []

    def fake_export(model, args, f, dynamo=None, **kwargs):
        if dynamo is not None:
            kwargs["dynamo"] = dynamo
        calls.append(kwargs)
        if kwargs.get("dynamo"):
            raise RuntimeError("dynamo broken")
        Path(f).write_bytes(b"onnx-bytes")

    class NoGrad:
        def __enter__(self): return None
        def __exit__(self, exc_type, exc, tb): return False

    fake_onnx_ns = types.SimpleNamespace(export=fake_export)
    fake_torch = types.ModuleType("torch")
    fake_torch.float16 = "fp16"
    fake_torch.no_grad = lambda: NoGrad()
    fake_torch.onnx = fake_onnx_ns

    fake_transformers = types.ModuleType("transformers")
    fake_transformers.AutoTokenizer = types.SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: FakeTokenizer()
    )
    fake_transformers.AutoModelForCausalLM = types.SimpleNamespace(
        from_pretrained=lambda *args, **kwargs: FakeModel()
    )

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    out_path = tmp_path / "model.onnx"
    result = convert_to_onnx(str(model_dir), str(out_path))
    assert out_path.exists()
    assert result["export_method"] == "torch.onnx.export:legacy"
    assert len(calls) == 2


def test_verify_onnx_dryrun():
    result = verify_onnx("", dry_run=True)
    assert result["all_pass"] is True
