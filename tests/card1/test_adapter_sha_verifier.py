from pathlib import Path

import pytest

from src.butler.card1.safety.adapter_sha_verifier import verify_adapter_sha256


def test_adapter_sha_verifier_accepts_matching_file(tmp_path: Path):
    adapter = tmp_path / "adapters.safetensors"
    adapter.write_bytes(b"card1-adapter-fixture")
    expected = "d22d09fadcc0a027f8d93875aab49fa89aaafe70c6eb1ffda1663faafb9f1941"

    result = verify_adapter_sha256(adapter, expected)

    assert result.ok is True
    assert result.actual_sha256 == expected


def test_adapter_sha_verifier_rejects_mismatch(tmp_path: Path):
    adapter = tmp_path / "adapters.safetensors"
    adapter.write_bytes(b"card1-adapter-fixture")

    with pytest.raises(ValueError, match="mismatch"):
        verify_adapter_sha256(adapter, "0" * 64)


def test_adapter_sha_verifier_requires_full_sha(tmp_path: Path):
    adapter = tmp_path / "adapters.safetensors"
    adapter.write_bytes(b"card1-adapter-fixture")

    with pytest.raises(ValueError, match="64-char"):
        verify_adapter_sha256(adapter, "abc")
