from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.convert import StructureOrInputError
from scripts.convert.convert_package_v2 import create_package


def test_create_package_requires_tokenizer(tmp_path: Path):
    mnn_path = tmp_path / "a.mnn"
    mnn_path.write_bytes(b"mnn")
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    with pytest.raises(StructureOrInputError):
        create_package(
            str(mnn_path),
            str(model_dir),
            str(tmp_path / "pkg"),
            "v1",
            onnx_digest="a" * 16,
            merged_digest="b" * 16,
        )


def test_create_package_success(tmp_path: Path):
    mnn_path = tmp_path / "a.mnn"
    mnn_path.write_bytes(b"mnn")
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    (model_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "generation_config.json").write_text("{}", encoding="utf-8")

    result = create_package(
        str(mnn_path),
        str(model_dir),
        str(tmp_path / "pkg"),
        "v1",
        onnx_digest="a" * 16,
        merged_digest="b" * 16,
        external_data_used=True,
    )
    manifest_path = tmp_path / "pkg" / "package_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["external_data_used"] is True
    assert manifest["tokenizer_file_digests"]["tokenizer.json"]
    assert manifest["config_file_digests"]["config.json"]
    assert result["generation_config_digest"]
