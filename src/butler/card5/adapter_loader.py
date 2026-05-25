from __future__ import annotations

import hashlib
import os
from pathlib import Path

EXPECTED_ADAPTER_SHA256 = "5b7806bdfece1b4cee61486998a0396194562da459e23aaa2094d55474d72135"
EXPECTED_ADAPTER_SIZE = 19_947_012
DEFAULT_ADAPTER_PATH = Path(
    os.environ.get(
        "BUTLER_CARD5_ADAPTER_PATH",
        str(
            Path.home()
            / "Desktop/butler-data/27_accounting_train/models"
            / "butler-1.7b-v6-card5-accounting-lora-v3-3"
            / "adapters.safetensors"
        ),
    )
)


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_and_locate_adapter(adapter_path: Path | None = None) -> Path:
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
