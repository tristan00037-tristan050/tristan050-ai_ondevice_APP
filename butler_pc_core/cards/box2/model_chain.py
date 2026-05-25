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


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_first_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    if path.is_file():
        return path
    for child in sorted(path.rglob("*")):
        if child.is_file():
            return child
    return None


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

    if not base_loaded:
        return ModelChainStatus(False, False, False, False, "contract_only" if allow_contract_only else "blocked", "BLOCK_BASE_MODEL_MISSING")
    if not butler_loaded:
        return ModelChainStatus(True, False, False, False, "contract_only" if allow_contract_only else "blocked", "BLOCK_BUTLER_V3_ADAPTER_MISSING")
    if not helper_loaded:
        return ModelChainStatus(True, True, False, False, "contract_only" if allow_contract_only else "blocked", "BLOCK_HELPER3_ADAPTER_MISSING")

    helper_file = _find_first_file(helper3_path)
    if helper_file is None:
        return ModelChainStatus(True, True, False, False, "blocked", "BLOCK_HELPER3_ADAPTER_MISSING")
    actual = _sha256_file(helper_file)
    if actual != expected_helper3_sha:
        return ModelChainStatus(True, True, True, False, "blocked", "BLOCK_ADAPTER_SHA_MISMATCH")

    return ModelChainStatus(True, True, True, True, "real", None)


def sealed_sha_summary() -> dict[str, str]:
    return {
        "helper_3_rewrite_adapter_sha": HELPER3_REWRITE_ADAPTER_SHA,
        "butler_v3_f16_gguf_sha": BUTLER_V3_F16_GGUF_SHA,
        "butler_v3_q4_k_m_gguf_sha": BUTLER_V3_Q4_K_M_GGUF_SHA,
    }
