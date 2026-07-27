from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from butler_pc_core.assets.contracts import AssetIdentity, NativeReadHandle
from butler_pc_core.assets.snapshot import _darwin_snapshot
from butler_pc_core.inference.verified_model_loader import (
    AFTER_AUTHORITY_VERIFY,
    AFTER_MMAP_BEFORE_PARSE,
    AFTER_PARSE,
    BEFORE_NATIVE_OPEN,
    DURING_NATIVE_READ,
    VerifiedLlamaLoader,
)


class _Backend:
    pass


pytestmark = pytest.mark.no_sidecar_token


def _handle(tmp_path: Path, payload: bytes) -> tuple[Path, NativeReadHandle]:
    source = tmp_path / "model.gguf"
    source.write_bytes(payload)
    source_fd = os.open(source, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    snapshot = _darwin_snapshot(source_fd, len(payload), tmp_path)
    os.close(source_fd)
    identity = AssetIdentity(
        role="box3.model",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        format="gguf",
        manifest_set_sha256="a" * 64,
    )
    return source, NativeReadHandle(
        snapshot.fd,
        identity=identity,
        seal_type=snapshot.seal_type,
    )


def test_macos_loader_maps_verified_native_object(tmp_path: Path) -> None:
    payload = b"verified-native-object"
    source, handle = _handle(tmp_path, payload)
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
            source.write_bytes(b"attacker-replacement")

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
            AFTER_MMAP_BEFORE_PARSE,
            AFTER_PARSE,
        ]
        assert session.receipt.platform_seal == "macos_native_mapping"
        assert session.receipt.asset_sha256 == session.receipt.mapped_asset_sha256
    finally:
        session.close()
        handle.close()


def test_macos_retained_writer_is_blocked_before_parse(tmp_path: Path) -> None:
    payload = b"read-only-native-object"
    _source, handle = _handle(tmp_path, payload)
    backend_calls = 0
    write_blocked = False

    def backend_provider():
        def factory(**_kwargs):
            nonlocal backend_calls
            backend_calls += 1
            return _Backend()

        return factory, "b" * 64, "c" * 64

    def observer(stage: str, _metadata: object) -> None:
        nonlocal write_blocked
        if stage == BEFORE_NATIVE_OPEN:
            try:
                os.write(handle.fd, b"x")
            except OSError:
                write_blocked = True

    session = VerifiedLlamaLoader(backend_provider).load_from_verified_handle(
        handle,
        n_ctx=512,
        n_threads=1,
        observer=observer,
    )
    try:
        assert write_blocked
        assert backend_calls == 1
    finally:
        session.close()
        handle.close()
