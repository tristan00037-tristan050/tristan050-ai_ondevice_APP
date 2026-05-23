from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from butler_pc_core.fail_class import FailClass
from butler_pc_core.integrity.model_pack_verifier import ModelPackVerifier


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes = b"fixture") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(data)


def test_manifest_load_success(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema": "model_pack.v1"}), encoding="utf-8")
    parsed, result = ModelPackVerifier(tmp_path).load_manifest(manifest)
    assert parsed == {"schema": "model_pack.v1"}
    assert result.ok is True
    assert "manifest_sha" in result.details
    assert result.verified_at


def test_manifest_load_missing(tmp_path: Path):
    parsed, result = ModelPackVerifier(tmp_path).load_manifest(tmp_path / "missing.json")
    assert parsed is None
    assert result.ok is False
    assert result.fail_class == FailClass.MODEL_PACK_MISSING
    assert "raw_file_content" not in result.details


def test_model_pack_sha_match(tmp_path: Path):
    expected = _write(tmp_path / "model.gguf", b"model")
    result = ModelPackVerifier(tmp_path).verify_file("model.gguf", expected, FailClass.MODEL_PACK_SHA_MISMATCH)
    assert result.ok is True
    assert result.details["actual_sha"] == expected


def test_model_pack_sha_mismatch(tmp_path: Path):
    _write(tmp_path / "model.gguf", b"model")
    result = ModelPackVerifier(tmp_path).verify_file("model.gguf", "0" * 64, FailClass.MODEL_PACK_SHA_MISMATCH)
    assert result.ok is False
    assert result.fail_class == FailClass.MODEL_PACK_SHA_MISMATCH
    assert "actual_sha" in result.details
    assert "file_size" in result.details


def test_adapter_sha_match(tmp_path: Path):
    expected = _write(tmp_path / "adapter.safetensors", b"adapter")
    result = ModelPackVerifier(tmp_path).verify_file("adapter.safetensors", expected, FailClass.ADAPTER_SHA_MISMATCH)
    assert result.ok is True


def test_adapter_sha_mismatch(tmp_path: Path):
    _write(tmp_path / "adapter.safetensors", b"adapter")
    result = ModelPackVerifier(tmp_path).verify_file("adapter.safetensors", "1" * 64, FailClass.ADAPTER_SHA_MISMATCH)
    assert result.ok is False
    assert result.fail_class == FailClass.ADAPTER_SHA_MISMATCH


def test_tokenizer_sha_match(tmp_path: Path):
    expected = _write(tmp_path / "tokenizer.json", b"tokenizer")
    result = ModelPackVerifier(tmp_path).verify_file("tokenizer.json", expected, FailClass.TOKENIZER_SHA_MISMATCH)
    assert result.ok is True


def test_verify_all_pass_fail(tmp_path: Path):
    model_sha = _write(tmp_path / "m.gguf", b"m")
    adapter_sha = _write(tmp_path / "a.bin", b"a")
    tokenizer_sha = _write(tmp_path / "t.json", b"t")
    verifier = ModelPackVerifier(tmp_path)
    ok = verifier.verify_all({
        "model_path": "m.gguf",
        "model_sha256": model_sha,
        "adapter_path": "a.bin",
        "adapter_sha256": adapter_sha,
        "tokenizer_path": "t.json",
        "tokenizer_sha256": tokenizer_sha,
    })
    assert ok.ok is True
    bad = verifier.verify_all({"model_path": "m.gguf", "model_sha256": "2" * 64})
    assert bad.ok is False
    assert bad.fail_class == FailClass.MODEL_PACK_SHA_MISMATCH


def test_manifest_path_traversal_blocked(tmp_path: Path):
    outside = tmp_path.parent / "outside.bin"
    outside.write_bytes(b"outside")
    result = ModelPackVerifier(tmp_path).verify_file("../outside.bin", _sha(b"outside"), FailClass.MODEL_PACK_SHA_MISMATCH)
    assert result.ok is False
    assert result.fail_class == FailClass.SIGNATURE_INVALID
    assert "outside base_dir" in result.details["reason"]


def test_symlink_blocked_by_default(tmp_path: Path):
    target = tmp_path / "target.bin"
    target.write_bytes(b"target")
    link = tmp_path / "link.bin"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        return
    result = ModelPackVerifier(tmp_path).verify_file("link.bin", _sha(b"target"), FailClass.MODEL_PACK_SHA_MISMATCH)
    assert result.ok is False
    assert result.fail_class == FailClass.SIGNATURE_INVALID
    assert result.details["reason"] == "symlink blocked"
