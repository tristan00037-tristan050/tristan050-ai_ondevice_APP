from pathlib import Path

import pytest

from butler.card5 import adapter_loader


def test_adapter_missing_fails(tmp_path: Path):
    with pytest.raises(RuntimeError, match="adapter not found"):
        adapter_loader.verify_and_locate_adapter(tmp_path / "missing.safetensors")


def test_adapter_size_mismatch_fails(tmp_path: Path):
    p = tmp_path / "adapters.safetensors"
    p.write_bytes(b"bad")
    with pytest.raises(RuntimeError, match="size mismatch"):
        adapter_loader.verify_and_locate_adapter(p)


def test_adapter_sha_mismatch_fails(monkeypatch, tmp_path: Path):
    p = tmp_path / "adapters.safetensors"
    p.write_bytes(b"x" * 4)

    monkeypatch.setattr(adapter_loader, "EXPECTED_ADAPTER_SIZE", 4)
    monkeypatch.setattr(adapter_loader, "EXPECTED_ADAPTER_SHA256", "0" * 64)

    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        adapter_loader.verify_and_locate_adapter(p)


def test_adapter_sha_matches_with_mocked_expected(monkeypatch, tmp_path: Path):
    p = tmp_path / "adapters.safetensors"
    p.write_bytes(b"verified-adapter")

    sha = adapter_loader.compute_sha256(p)

    monkeypatch.setattr(adapter_loader, "EXPECTED_ADAPTER_SIZE", p.stat().st_size)
    monkeypatch.setattr(adapter_loader, "EXPECTED_ADAPTER_SHA256", sha)

    assert adapter_loader.verify_and_locate_adapter(p) == p
