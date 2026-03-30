from __future__ import annotations

from pathlib import Path

import pytest

from scripts.convert import StructureOrInputError
from scripts.convert.convert_ort_mobile_v1 import convert_to_ort


def test_convert_to_ort_missing_onnx_raises(tmp_path: Path):
    with pytest.raises(StructureOrInputError):
        convert_to_ort(str(tmp_path / "missing.onnx"), str(tmp_path / "out" / "model.ort"))


def test_convert_to_ort_skips_without_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    onnx_path = tmp_path / "model.onnx"
    onnx_path.write_bytes(b"onnx")
    monkeypatch.setattr("scripts.convert.convert_ort_mobile_v1._load_ort_converter", lambda: None)
    result = convert_to_ort(str(onnx_path), str(tmp_path / "ort" / "model.ort"))
    assert result["skipped"] is True


def test_convert_to_ort_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    onnx_path = tmp_path / "model.onnx"
    onnx_path.write_bytes(b"onnx")
    out_dir = tmp_path / "ort"

    class FakeModule:
        @staticmethod
        def convert_onnx_models_to_ort(model_path_or_dir, output_dir=None, optimization_style="Fixed", **kwargs):
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            Path(output_dir, "model.ort").write_bytes(b"ort")

    monkeypatch.setattr("scripts.convert.convert_ort_mobile_v1._load_ort_converter", lambda: FakeModule())
    result = convert_to_ort(str(onnx_path), str(out_dir / "model.ort"))
    assert result["skipped"] is False
    assert (out_dir / "model.ort").exists()
    assert result["ort_digest"]
