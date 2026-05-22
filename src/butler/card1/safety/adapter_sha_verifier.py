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
    # SHA-256 hex digest 정규화 (Codex P2, PR #749):
    #   - hexdigest()는 stdlib 계약상 항상 소문자 반환
    #   - expected_sha256은 runbook/툴링/수기 입력에서 대소문자 혼재 + 공백 가능
    #   - 관례상 SHA hex는 case-insensitive → 양쪽 모두 소문자 정규화
    #   - normalize 후 length 검증 + 비교 (일관성 본질)
    expected_normalized = expected_sha256.strip().lower()

    if len(expected_normalized) != 64:
        raise ValueError("expected_sha256 must be a full 64-char SHA-256")
    if not adapter_path.exists():
        raise ValueError(f"adapter file not found: {adapter_path}")
    if not adapter_path.is_file():
        raise ValueError(f"adapter path is not a file: {adapter_path}")

    actual = _sha256_file(adapter_path)
    if actual != expected_normalized:
        raise ValueError(
            f"adapter SHA-256 mismatch: expected={expected_normalized}, actual={actual}"
        )

    return AdapterShaVerification(
        adapter_path=str(adapter_path),
        expected_sha256=expected_sha256,
        actual_sha256=actual,
        ok=True,
    )
