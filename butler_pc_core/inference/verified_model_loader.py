from __future__ import annotations

import hashlib
import mmap
import os
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from butler_pc_core.assets import LoadedModelReceipt, NativeReadHandle

_CHUNK_BYTES = 8 * 1024 * 1024
BackendFactory = Callable[..., Any]
LoaderObserver = Callable[[str, Mapping[str, object]], None]

AFTER_AUTHORITY_VERIFY = "AFTER_AUTHORITY_VERIFY"
BEFORE_NATIVE_OPEN = "BEFORE_NATIVE_OPEN"
DURING_NATIVE_READ = "DURING_NATIVE_READ"
AFTER_MMAP_BEFORE_PARSE = "AFTER_MMAP_BEFORE_PARSE"
AFTER_PARSE = "AFTER_PARSE"


def _digest_handle(handle: NativeReadHandle) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with handle.open() as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _default_backend_factory() -> tuple[BackendFactory, str, str]:
    import llama_cpp  # type: ignore[import]
    from llama_cpp import Llama  # type: ignore[import]

    module_path = Path(llama_cpp.__file__ or "")
    if not module_path.is_absolute() or not module_path.is_file():
        raise RuntimeError("BLOCK_LOADER_BACKEND_UNVERIFIED")
    loader_digest = _file_sha256(Path(__file__).resolve())
    native_candidates = sorted(
        path
        for path in module_path.parent.rglob("*")
        if path.is_file() and path.suffix.casefold() in {".dylib", ".so", ".dll", ".pyd"}
    )
    if not native_candidates:
        raise RuntimeError("BLOCK_NATIVE_BACKEND_UNVERIFIED")
    native_digest = hashlib.sha256(
        b"".join(bytes.fromhex(_file_sha256(path)) for path in native_candidates)
    ).hexdigest()
    return Llama, loader_digest, native_digest


def _notify(
    observer: LoaderObserver | None,
    stage: str,
    **metadata: object,
) -> None:
    if observer is not None:
        observer(stage, metadata)


def _map_and_digest(
    handle: NativeReadHandle,
    *,
    observer: LoaderObserver | None,
) -> tuple[mmap.mmap, str, int]:
    length = handle.identity.size_bytes
    if length <= 0:
        raise RuntimeError("BLOCK_LOADER_OBJECT_MISMATCH")
    _notify(
        observer,
        BEFORE_NATIVE_OPEN,
        asset_role=handle.identity.role,
        expected_length=length,
    )
    mapping = mmap.mmap(handle.fd, length, access=mmap.ACCESS_READ)
    try:
        digest = hashlib.sha256()
        processed = 0
        while processed < length:
            end = min(processed + _CHUNK_BYTES, length)
            digest.update(mapping[processed:end])
            processed = end
            _notify(
                observer,
                DURING_NATIVE_READ,
                asset_role=handle.identity.role,
                bytes_processed=processed,
                mapped_length=length,
            )
        mapped_digest = digest.hexdigest()
        _notify(
            observer,
            AFTER_MMAP_BEFORE_PARSE,
            asset_role=handle.identity.role,
            mapped_asset_sha256=mapped_digest,
            mapped_length=length,
        )
        return mapping, mapped_digest, length
    except Exception:
        mapping.close()
        raise


class VerifiedLlamaSession:
    __slots__ = ("backend", "receipt", "_handle", "_mapping")

    def __init__(
        self,
        *,
        backend: Any,
        receipt: LoadedModelReceipt,
        handle: NativeReadHandle,
        mapping: mmap.mmap,
    ) -> None:
        self.backend = backend
        self.receipt = receipt
        self._handle = handle
        self._mapping = mapping

    def close(self) -> None:
        self.backend = None
        self._mapping.close()
        self._handle.close()

    def __del__(self) -> None:
        try:
            self.close()
        except OSError:
            pass


class VerifiedLlamaLoader:
    """The only product adapter allowed to invoke llama.cpp."""

    def __init__(
        self,
        backend_provider: Callable[[], tuple[BackendFactory, str, str]] | None = None,
    ) -> None:
        self._backend_provider = backend_provider or _default_backend_factory

    def load_from_verified_handle(
        self,
        handle: NativeReadHandle,
        *,
        n_ctx: int,
        n_threads: int,
        observer: LoaderObserver | None = None,
    ) -> VerifiedLlamaSession:
        owned = handle.duplicate()
        mapping: mmap.mmap | None = None
        try:
            before_digest, before_length = _digest_handle(owned)
            identity = owned.identity
            if (
                before_length != identity.size_bytes
                or not secrets.compare_digest(before_digest, identity.sha256)
            ):
                raise RuntimeError("BLOCK_LOADER_OBJECT_MISMATCH")
            _notify(
                observer,
                AFTER_AUTHORITY_VERIFY,
                asset_role=identity.role,
                asset_sha256=before_digest,
                asset_length=before_length,
            )
            mapping, mapped_digest, mapped_length = _map_and_digest(
                owned,
                observer=observer,
            )
            if (
                mapped_length != before_length
                or not secrets.compare_digest(mapped_digest, before_digest)
            ):
                raise RuntimeError("BLOCK_LOADER_OBJECT_MISMATCH")
            factory, loader_digest, native_digest = self._backend_provider()
            descriptor_ref = (
                f"/dev/fd/{owned.fd}"
                if sys.platform == "darwin"
                else f"/proc/self/fd/{owned.fd}"
                if sys.platform.startswith("linux")
                else ""
            )
            if not descriptor_ref:
                raise RuntimeError("BLOCK_PLATFORM_UNSUPPORTED")
            os.lseek(owned.fd, 0, os.SEEK_SET)
            backend = factory(
                **{
                    "model_path": descriptor_ref,
                    "n_ctx": n_ctx,
                    "n_threads": n_threads,
                    "verbose": False,
                }
            )
            after_digest, after_length = _digest_handle(owned)
            if after_length != mapped_length or not secrets.compare_digest(
                after_digest, mapped_digest
            ):
                raise RuntimeError("BLOCK_LOADER_OBJECT_MISMATCH")
            _notify(
                observer,
                AFTER_PARSE,
                asset_role=identity.role,
                mapped_asset_sha256=mapped_digest,
                mapped_length=mapped_length,
            )
            receipt = LoadedModelReceipt(
                schema_version=1,
                run_id=str(uuid.uuid4()),
                nonce=secrets.token_hex(32),
                asset_role=identity.role,
                asset_sha256=identity.sha256,
                mapped_asset_sha256=mapped_digest,
                mapped_length=mapped_length,
                loader_binary_sha256=loader_digest,
                native_backend_sha256=native_digest,
                platform_seal=owned.seal_type,
                result="ALLOW",
                reason_code="OK",
            )
            return VerifiedLlamaSession(
                backend=backend,
                receipt=receipt,
                handle=owned,
                mapping=mapping,
            )
        except Exception:
            if mapping is not None:
                mapping.close()
            owned.close()
            raise
