from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from butler_pc_core.assets.contracts import AssetIdentity, NativeReadHandle
from butler_pc_core.assets.snapshot import _linux_snapshot
from butler_pc_core.inference.verified_model_loader import (
    AFTER_AUTHORITY_VERIFY,
    AFTER_MMAP_BEFORE_PARSE,
    AFTER_PARSE,
    BEFORE_NATIVE_OPEN,
    DURING_NATIVE_READ,
    VerifiedLlamaLoader,
)


ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.no_sidecar_token


class _Backend:
    pass


def test_linux_loader_maps_sealed_memfd(tmp_path: Path) -> None:
    if not hasattr(os, "memfd_create"):
        assert "os.memfd_create" in inspect.getsource(_linux_snapshot)
        assert "F_ADD_SEALS" in inspect.getsource(_linux_snapshot)
        return
    payload = b"G" * (9 * 1024 * 1024)
    source = tmp_path / "model.gguf"
    source.write_bytes(payload)
    source_fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    snapshot = _linux_snapshot(source_fd, len(payload))
    os.close(source_fd)
    identity = AssetIdentity(
        role="free_chat.model",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        format="gguf",
        manifest_set_sha256="a" * 64,
    )
    handle = NativeReadHandle(snapshot.fd, identity=identity, seal_type=snapshot.seal_type)
    parsed: list[bytes] = []

    def backend_provider():
        def factory(**kwargs):
            parsed.append(Path(kwargs["model_path"]).read_bytes())
            return _Backend()

        return factory, "b" * 64, "c" * 64

    stages: list[str] = []

    def observer(stage: str, _metadata: object) -> None:
        stages.append(stage)
        if stage == AFTER_AUTHORITY_VERIFY:
            source.unlink()
            source.write_bytes(b"X" * len(payload))

    session = VerifiedLlamaLoader(backend_provider).load_from_verified_handle(
        handle,
        n_ctx=512,
        n_threads=1,
        observer=observer,
    )
    try:
        assert parsed == [payload]
        assert stages == [
            AFTER_AUTHORITY_VERIFY,
            BEFORE_NATIVE_OPEN,
            DURING_NATIVE_READ,
            DURING_NATIVE_READ,
            AFTER_MMAP_BEFORE_PARSE,
            AFTER_PARSE,
        ]
        receipt = session.receipt.to_dict()
        assert receipt["asset_sha256"] == receipt["mapped_asset_sha256"]
        assert receipt["platform_seal"] == "linux_memfd"
        schema = json.loads(
            (ROOT / "contracts/assets/loaded-model-receipt-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(receipt)
    finally:
        session.close()
        handle.close()
