from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from butler_pc_core.assets.contracts import AssetIdentity, NativeReadHandle
from butler_pc_core.inference.verified_model_loader import VerifiedLlamaLoader
from scripts import verify_asset_consumer_inventory
from scripts.verify_asset_consumer_inventory import audit_inventory


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.no_sidecar_token


def test_all_language_loaders_are_inventoried() -> None:
    inventory, scan = audit_inventory()
    sources = {row["source_path"] for row in inventory["consumers"]}
    assert set(scan.python_model_loader_imports) == {
        "butler_pc_core/inference/verified_model_loader.py"
    }
    assert set(scan.python_model_loader_imports) <= sources
    assert set(scan.native_command_sources) <= sources
    assert all(row["authority_api"] == "AssetAuthority.acquire" for row in inventory["consumers"])


def test_receipt_binds_explicit_control_head_not_reserved_github_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = verify_asset_consumer_inventory._git("rev-parse", "HEAD")
    monkeypatch.setenv("GITHUB_SHA", "f" * len(head))
    monkeypatch.setenv("ASSET_CONTROL_PLANE_SHA", head)
    receipt = tmp_path / "receipt.json"
    monkeypatch.setenv("ASSET_INVENTORY_RECEIPT_OUT", str(receipt))

    assert verify_asset_consumer_inventory.main() == 0
    assert receipt.is_file()


def test_authority_block_means_zero_loader_invocations(tmp_path: Path) -> None:
    backend_calls = 0

    def backend_provider():
        nonlocal backend_calls
        backend_calls += 1
        raise AssertionError("backend must not be reached")

    payload = b"unapproved-model"
    source = tmp_path / "model.gguf"
    source.write_bytes(payload)
    fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    handle = NativeReadHandle(
        fd,
        identity=AssetIdentity(
            role="free_chat.model",
            sha256="0" * 64,
            size_bytes=len(payload),
            format="gguf",
            manifest_set_sha256="a" * 64,
        ),
        seal_type="linux_memfd",
    )
    try:
        with pytest.raises(RuntimeError, match="BLOCK_LOADER_OBJECT_MISMATCH"):
            VerifiedLlamaLoader(backend_provider).load_from_verified_handle(
                handle,
                n_ctx=512,
                n_threads=1,
            )
    finally:
        handle.close()
    assert backend_calls == 0
