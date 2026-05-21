"""Card 5 adapter 안전 로드.

본 모듈은 adapter binary를 repo에 넣지 않고, 로컬 on-device 경로에서만
크기와 SHA-256을 검증한 뒤 사용할 수 있게 한다.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

EXPECTED_ADAPTER_SHA256 = "9f167c7e63825e416ee8743f78549cb51e1108e5b111f3a1eb3db07422ea2ab2"
EXPECTED_ADAPTER_SIZE = 79_716_252

DEFAULT_ADAPTER_PATH = Path(
    os.environ.get(
        "BUTLER_CARD5_ADAPTER_PATH",
        str(
            Path.home()
            / "Desktop/butler-data/27_accounting_train/models"
            / "butler-1.7b-v3-card5-accounting-lora-v2"
            / "adapters.safetensors"
        ),
    )
)


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_and_locate_adapter(adapter_path: Path | None = None) -> Path:
    """Fail-closed adapter 검증.

    검증 항목:
    - 파일 존재
    - 파일 크기
    - SHA-256
    """
    path = adapter_path or DEFAULT_ADAPTER_PATH

    if not path.exists():
        raise RuntimeError(f"BLOCK: adapter not found: {path}")

    actual_size = path.stat().st_size
    if actual_size != EXPECTED_ADAPTER_SIZE:
        raise RuntimeError(
            f"BLOCK: adapter size mismatch: expected={EXPECTED_ADAPTER_SIZE}, got={actual_size}"
        )

    actual_sha = compute_sha256(path)
    if actual_sha != EXPECTED_ADAPTER_SHA256:
        raise RuntimeError(
            "BLOCK: adapter SHA-256 mismatch: "
            f"expected={EXPECTED_ADAPTER_SHA256}, got={actual_sha}"
        )

    return path
