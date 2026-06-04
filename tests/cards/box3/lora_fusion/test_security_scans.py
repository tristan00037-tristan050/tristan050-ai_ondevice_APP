from __future__ import annotations

import os
from pathlib import Path

import pytest

from butler_pc_core.cards.box3.lora_fusion.security import assert_no_raw_or_path_material


def test_raw_path_secret_scan_blocks_sensitive_fields():
    with pytest.raises(ValueError):
        assert_no_raw_or_path_material({"raw_prompt": "hello"})


def test_path_scan_blocks_absolute_path():
    with pytest.raises(ValueError):
        assert_no_raw_or_path_material({"some_digest": "sha256:" + "0"*64, "note": "/Users/example/model.gguf"})


def test_no_connect_loop_contract_files_in_package():
    root = Path(__file__).resolve().parents[3]
    assert not (root / "schemas" / "connect_loop").exists()
    assert not (root / "docs" / "ssot").exists()


def test_no_binary_or_training_artifact_references():
    root = Path(__file__).resolve().parents[3] / "butler_pc_core" / "cards" / "box3" / "lora_fusion"
    text = "\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    forbidden = ["Trainer(", "save_pretrained", ".safetensors", ".gguf"]
    assert not any(item in text for item in forbidden)
