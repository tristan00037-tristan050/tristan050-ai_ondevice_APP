from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

BASE_MODEL_PATH = Path.home() / "Desktop/도우미폴더/Qwen3-1.7B"
BUTLER_V3_ADAPTER_PATH = Path.home() / "Desktop/도우미폴더/butler-qwen3-1.7b-v3/lora_adapter"
HELPER3_ADAPTER_PATH = Path.home() / "Desktop/도우미폴더/box2b_v5_outputs/rewrite/adapter/box2b_v5_rewrite"

HELPER3_REWRITE_ADAPTER_SHA = "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0"
BUTLER_V3_F16_GGUF_SHA = "46e75f40cd6b37fb26bcc7fb21fb375af05abb5b6eceeef00c7d85e4092f381d"
BUTLER_V3_Q4_K_M_GGUF_SHA = "80a76db71f7218d84aadc6f1db59339b235f1eceff42be7cdbf9e4c60a5950dd"

LoadMode = Literal["real", "contract_only", "blocked"]


@dataclass(frozen=True)
class ModelChainStatus:
    base_model_loaded: bool
    butler_v3_loaded: bool
    helper_3_loaded: bool
    helper_3_sha_verified: bool
    load_mode: LoadMode
    fail_class: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _hash_file_into_digest(digest: "hashlib._Hash", path: Path, rel_path: str) -> None:
    digest.update(rel_path.encode("utf-8"))
    digest.update(b"\0")
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    digest.update(b"\0")


def sha256_path(path: Path) -> str:
    """Return a stable digest for a single file or an adapter directory.

    Directory hashing includes relative file paths and file bytes in sorted order, so
    moving, adding, deleting, or modifying adapter files changes the digest. This is
    intentionally stricter than hashing the first file found in the adapter folder.
    """
    digest = hashlib.sha256()
    if path.is_file():
        _hash_file_into_digest(digest, path, path.name)
        return digest.hexdigest()

    files = [child for child in sorted(path.rglob("*")) if child.is_file()]
    if not files:
        return ""
    for child in files:
        _hash_file_into_digest(digest, child, child.relative_to(path).as_posix())
    return digest.hexdigest()


def inspect_model_chain(
    base_path: Path = BASE_MODEL_PATH,
    butler_v3_path: Path = BUTLER_V3_ADAPTER_PATH,
    helper3_path: Path = HELPER3_ADAPTER_PATH,
    expected_helper3_sha: str = HELPER3_REWRITE_ADAPTER_SHA,
    allow_contract_only: bool = True,
) -> ModelChainStatus:
    base_loaded = base_path.exists()
    butler_loaded = butler_v3_path.exists()
    helper_loaded = helper3_path.exists()

    missing_mode: LoadMode = "contract_only" if allow_contract_only else "blocked"
    if not base_loaded:
        return ModelChainStatus(False, False, False, False, missing_mode, "BLOCK_BASE_MODEL_MISSING")
    if not butler_loaded:
        return ModelChainStatus(True, False, False, False, missing_mode, "BLOCK_BUTLER_V3_ADAPTER_MISSING")
    if not helper_loaded:
        return ModelChainStatus(True, True, False, False, missing_mode, "BLOCK_HELPER3_ADAPTER_MISSING")

    actual = sha256_path(helper3_path)
    if not actual:
        return ModelChainStatus(True, True, False, False, "blocked", "BLOCK_HELPER3_ADAPTER_MISSING")
    if actual != expected_helper3_sha:
        return ModelChainStatus(True, True, True, False, "blocked", "BLOCK_ADAPTER_SHA_MISMATCH")

    return ModelChainStatus(True, True, True, True, "real", None)


def sealed_sha_summary() -> dict[str, str]:
    return {
        "helper_3_rewrite_adapter_sha": HELPER3_REWRITE_ADAPTER_SHA,
        "butler_v3_f16_gguf_sha": BUTLER_V3_F16_GGUF_SHA,
        "butler_v3_q4_k_m_gguf_sha": BUTLER_V3_Q4_K_M_GGUF_SHA,
    }
