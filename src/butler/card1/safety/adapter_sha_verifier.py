"""Card 1 adapter SHA verifier.

The actual Card 1 adapter artifact is outside the repository. This module is
strictly fail-closed: a caller must provide the expected full SHA-256 and an
existing adapter path. The verifier never downloads adapters and never accepts
partial hashes.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


CARD1_ADAPTER_RELATIVE_HINT = "~/Desktop/butler-data/card1_request_core/models/adapters.safetensors"


@dataclass(frozen=True)
class AdapterShaVerification:
    adapter_path: str
    expected_sha256: str
    actual_sha256: str
    ok: bool


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_adapter_sha256(adapter_path: Path, expected_sha256: str) -> AdapterShaVerification:
    if len(expected_sha256) != 64:
        raise ValueError("expected_sha256 must be a full 64-char SHA-256")
    if not adapter_path.exists():
        raise ValueError(f"adapter file not found: {adapter_path}")
    if not adapter_path.is_file():
        raise ValueError(f"adapter path is not a file: {adapter_path}")

    actual = _sha256_file(adapter_path)
    if actual != expected_sha256:
        raise ValueError(f"adapter SHA-256 mismatch: expected={expected_sha256}, actual={actual}")

    return AdapterShaVerification(
        adapter_path=str(adapter_path),
        expected_sha256=expected_sha256,
        actual_sha256=actual,
        ok=True,
    )
