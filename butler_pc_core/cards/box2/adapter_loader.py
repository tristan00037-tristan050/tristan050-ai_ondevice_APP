from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from butler_pc_core.assets import AssetError, get_asset_service

DEFAULT_HANDOFF_ROOT = "asset://box2.adapter"
DEFAULT_BASE_MODEL_PATH = f"{DEFAULT_HANDOFF_ROOT}/base_model"
DEFAULT_BUTLER_V3_LORA_PATH = f"{DEFAULT_HANDOFF_ROOT}/butler_adapter"
DEFAULT_BUTLER_V3_GGUF_F16_PATH = f"{DEFAULT_HANDOFF_ROOT}/model_f16"
DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH = f"{DEFAULT_HANDOFF_ROOT}/model_q4"
DEFAULT_HELPER_3_PATH = f"{DEFAULT_HANDOFF_ROOT}/rewrite_adapter"

BUTLER_V3_LORA_ADAPTER_SHA = "ee35fe47c2421df18597dd9939a08b4ff3bf4e25b8766ba5d914060ccaedd284"
BUTLER_V3_F16_GGUF_SHA = "46e75f40cd6b37fb26bcc7fb21fb375af05abb5b6eceeef00c7d85e4092f381d"
BUTLER_V3_Q4_K_M_GGUF_SHA = "80a76db71f7218d84aadc6f1db59339b235f1eceff42be7cdbf9e4c60a5950dd"
HELPER_3_REWRITE_ADAPTER_SHA = "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0"

PathKind = Literal["file", "directory", "directory_or_file"]
ShaScope = Literal["file", "directory_manifest", "unknown"]
@dataclass(frozen=True)
class AssetContract:
    name: str
    path: str
    path_kind: PathKind
    expected_sha256: str | None
    sha_scope: ShaScope

    @property
    def expanded_path(self):
        raise RuntimeError("ASSET_PATH_RECONSTRUCTION_FORBIDDEN")


@dataclass(frozen=True)
class AssetCheck:
    name: str
    path: str
    path_kind: str
    expected_sha256: str | None
    sha_scope: str
    exists: bool
    kind_ok: bool
    sha_checked: bool
    sha_match: bool | None
    actual_sha256: str | None
    resolved_digest_path: str | None
    status: str
    reason: str


def _sha256_is_full(value: str | None) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def asset_contracts() -> dict[str, AssetContract]:
    return {
        "base_model": AssetContract("base_model", DEFAULT_BASE_MODEL_PATH, "directory", None, "unknown"),
        "butler_v3_lora": AssetContract("butler_v3_lora", DEFAULT_BUTLER_V3_LORA_PATH, "directory", BUTLER_V3_LORA_ADAPTER_SHA, "file"),
        "butler_v3_gguf_f16": AssetContract("butler_v3_gguf_f16", DEFAULT_BUTLER_V3_GGUF_F16_PATH, "file", BUTLER_V3_F16_GGUF_SHA, "file"),
        "butler_v3_gguf_q4_k_m": AssetContract("butler_v3_gguf_q4_k_m", DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH, "file", BUTLER_V3_Q4_K_M_GGUF_SHA, "file"),
        "helper_3": AssetContract(
            "helper_3",
            f"{DEFAULT_HELPER_3_PATH}/adapter_model.safetensors",
            "file",
            HELPER_3_REWRITE_ADAPTER_SHA,
            "file",
        ),
        # NOTE (PR #754 follow-on P1):
        # sha_scope='file' 단독으로는 tamper 검출 보장 불가.
        # contract.path 자체가 실제 측정 대상 .safetensors 파일을
        # 가리켜야만 BLOCK_V2_SHA_MISMATCH(또는 v3 라벨)이 직접 raise됨.
        # 디렉토리 경로 + resolve_adapter_weight_file 간접 경유 방식은
        # digest=None PARTIAL_DONE → 우회 결함 재발 위험.
    }



ASSET_CONTRACTS = asset_contracts()

_ROLE_BY_CONTRACT = {
    "base_model": "base_model",
    "butler_v3_lora": "butler_adapter",
    "butler_v3_gguf_f16": "model_f16",
    "butler_v3_gguf_q4_k_m": "model_q4",
    "helper_3": "rewrite_adapter",
}


def check_asset(contract: AssetContract, *, allow_missing: bool = True) -> AssetCheck:
    if contract.expected_sha256 is not None and not _sha256_is_full(contract.expected_sha256):
        return AssetCheck(contract.name, contract.path, contract.path_kind, contract.expected_sha256, contract.sha_scope, True, True, False, None, None, None, "BLOCK_V3_SHA_CONTRACT_INVALID", "expected SHA-256 must be full lowercase 64-character digest")
    try:
        with get_asset_service().require_capability("box2.adapter") as lease:
            asset = lease.require(_ROLE_BY_CONTRACT[contract.name])
            actual = asset.entry.sha256
    except (AssetError, KeyError):
        return AssetCheck(
            contract.name,
            contract.path,
            contract.path_kind,
            contract.expected_sha256,
            contract.sha_scope,
            False,
            False,
            False,
            None,
            None,
            None,
            "MISSING_ALLOWED" if allow_missing else "BLOCK_ASSET_PATH_MISSING",
            "verified asset capability is unavailable",
        )
    match = contract.expected_sha256 is None or actual == contract.expected_sha256
    return AssetCheck(contract.name, contract.path, contract.path_kind, contract.expected_sha256, contract.sha_scope, True, True, contract.expected_sha256 is not None, match, actual, None, "PASS" if match else "BLOCK_V2_SHA_MISMATCH", "verified by sealed manifest" if contract.expected_sha256 is None else ("sha verified" if match else "sha mismatch"))


def verify_asset_contracts(*, allow_missing: bool = True) -> dict[str, AssetCheck]:
    return {name: check_asset(contract, allow_missing=allow_missing) for name, contract in asset_contracts().items()}


def sha_mismatch_count(checks: dict[str, AssetCheck]) -> int:
    return sum(1 for check in checks.values() if check.status in {"BLOCK_V2_SHA_MISMATCH", "BLOCK_V3_SHA_MISMATCH"})
