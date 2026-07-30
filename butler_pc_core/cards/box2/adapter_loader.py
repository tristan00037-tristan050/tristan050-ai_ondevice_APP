from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

_RESOURCE_ROOT = Path(__file__).resolve().parents[3]
_BOX2_ROOT_RELATIVE = Path("models/box2")
_BOX2_ADAPTER_RELATIVE = _BOX2_ROOT_RELATIVE / "box2_adapter"

DEFAULT_HANDOFF_ROOT = _BOX2_ROOT_RELATIVE.as_posix()
DEFAULT_BASE_MODEL_PATH = (
    _BOX2_ROOT_RELATIVE / "base" / "Qwen3-1.7B"
).as_posix()
DEFAULT_BUTLER_V3_LORA_PATH = (
    _BOX2_ADAPTER_RELATIVE
    / "rewrite"
    / "adapter"
    / "butler_v3_preserved"
).as_posix()
DEFAULT_BUTLER_V3_GGUF_F16_PATH = (
    _BOX2_ROOT_RELATIVE / "base" / "butler-1.7b-v3-f16.gguf"
).as_posix()
DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH = (
    _BOX2_ROOT_RELATIVE / "base" / "butler-1.7b-v3-q4_k_m.gguf"
).as_posix()
DEFAULT_HELPER_3_PATH = (
    _BOX2_ADAPTER_RELATIVE
    / "rewrite"
    / "adapter"
    / "box2b_v5_rewrite"
).as_posix()

_ENV_BY_ASSET = {
    "base_model": "BUTLER_BOX2_BASE_MODEL_PATH",
    "butler_v3_lora": "BUTLER_BOX2_BUTLER_V3_LORA_PATH",
    "butler_v3_gguf_f16": "BUTLER_BOX2_V3_GGUF_F16_PATH",
    "butler_v3_gguf_q4_k_m": "BUTLER_BOX2_V3_GGUF_Q4_K_M_PATH",
    "helper_3": "BUTLER_BOX2_HELPER3_ADAPTER_PATH",
}

_DEFAULT_BY_ASSET = {
    "base_model": DEFAULT_BASE_MODEL_PATH,
    "butler_v3_lora": DEFAULT_BUTLER_V3_LORA_PATH,
    "butler_v3_gguf_f16": DEFAULT_BUTLER_V3_GGUF_F16_PATH,
    "butler_v3_gguf_q4_k_m": DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH,
    "helper_3": DEFAULT_HELPER_3_PATH,
}

BUTLER_V3_LORA_ADAPTER_SHA = "ee35fe47c2421df18597dd9939a08b4ff3bf4e25b8766ba5d914060ccaedd284"
BUTLER_V3_F16_GGUF_SHA = "46e75f40cd6b37fb26bcc7fb21fb375af05abb5b6eceeef00c7d85e4092f381d"
BUTLER_V3_Q4_K_M_GGUF_SHA = "80a76db71f7218d84aadc6f1db59339b235f1eceff42be7cdbf9e4c60a5950dd"
HELPER_3_REWRITE_ADAPTER_SHA = "92e8454fdc01d9bb002a510b2fdaecabcc9b9cbf964b6e48e5d61c23b5ace4b0"

PathKind = Literal["file", "directory", "directory_or_file"]
ShaScope = Literal["file", "directory_manifest", "unknown"]
ADAPTER_WEIGHT_CANDIDATES = ("adapter_model.safetensors", "adapters.safetensors", "adapter.safetensors", "adapter_model.bin", "pytorch_model.bin")


@dataclass(frozen=True)
class AssetContract:
    name: str
    path: str
    path_source: Literal["environment", "bundle"]
    path_kind: PathKind
    expected_sha256: str | None
    sha_scope: ShaScope

    @property
    def expanded_path(self) -> Path:
        return Path(self.path).expanduser()


@dataclass(frozen=True)
class AssetCheck:
    name: str
    path_source: str
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


def _resolved_asset_path(name: str) -> tuple[Path, Literal["environment", "bundle"]]:
    configured = os.environ.get(_ENV_BY_ASSET[name], "").strip()
    if configured:
        return Path(configured).expanduser(), "environment"
    return _RESOURCE_ROOT / _DEFAULT_BY_ASSET[name], "bundle"


def resolved_asset_paths() -> dict[str, Path]:
    return {name: _resolved_asset_path(name)[0] for name in _DEFAULT_BY_ASSET}


def _sha256_is_full(value: str | None) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def compute_file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_manifest_entries(directory: Path) -> Iterable[tuple[str, str]]:
    for item in sorted(p for p in directory.rglob("*") if p.is_file()):
        yield item.relative_to(directory).as_posix(), compute_file_sha256(item)


def compute_directory_manifest_sha256(directory: Path) -> str:
    h = hashlib.sha256()
    for rel_path, file_sha in _iter_manifest_entries(directory):
        h.update(rel_path.encode("utf-8")); h.update(b"\0"); h.update(file_sha.encode("ascii")); h.update(b"\n")
    return h.hexdigest()


def resolve_adapter_weight_file(path: Path) -> Path | None:
    if path.is_file():
        return path
    if not path.is_dir():
        return None
    for candidate in ADAPTER_WEIGHT_CANDIDATES:
        target = path / candidate
        if target.is_file():
            return target
    safetensors = sorted(path.glob("*.safetensors"))
    if len(safetensors) == 1:
        return safetensors[0]
    bins = sorted(path.glob("*.bin"))
    if len(bins) == 1:
        return bins[0]
    return None


def asset_contracts() -> dict[str, AssetContract]:
    base_model, base_model_source = _resolved_asset_path("base_model")
    butler_v3_lora, butler_v3_lora_source = _resolved_asset_path("butler_v3_lora")
    butler_v3_gguf_f16, butler_v3_gguf_f16_source = _resolved_asset_path(
        "butler_v3_gguf_f16"
    )
    butler_v3_gguf_q4_k_m, butler_v3_gguf_q4_k_m_source = _resolved_asset_path(
        "butler_v3_gguf_q4_k_m"
    )
    helper_3, helper_3_source = _resolved_asset_path("helper_3")
    return {
        "base_model": AssetContract(
            "base_model", str(base_model), base_model_source, "directory", None, "unknown"
        ),
        "butler_v3_lora": AssetContract(
            "butler_v3_lora",
            str(butler_v3_lora),
            butler_v3_lora_source,
            "directory",
            BUTLER_V3_LORA_ADAPTER_SHA,
            "file",
        ),
        "butler_v3_gguf_f16": AssetContract(
            "butler_v3_gguf_f16",
            str(butler_v3_gguf_f16),
            butler_v3_gguf_f16_source,
            "file",
            BUTLER_V3_F16_GGUF_SHA,
            "file",
        ),
        "butler_v3_gguf_q4_k_m": AssetContract(
            "butler_v3_gguf_q4_k_m",
            str(butler_v3_gguf_q4_k_m),
            butler_v3_gguf_q4_k_m_source,
            "file",
            BUTLER_V3_Q4_K_M_GGUF_SHA,
            "file",
        ),
        "helper_3": AssetContract(
            "helper_3",
            str(helper_3 / "adapter_model.safetensors"),
            helper_3_source,
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

def kind_matches(path: Path, path_kind: PathKind) -> bool:
    return path.is_file() if path_kind == "file" else path.is_dir() if path_kind == "directory" else (path.is_file() or path.is_dir())


def compute_sha_for_contract(contract: AssetContract) -> tuple[str | None, Path | None]:
    path = contract.expanded_path
    if not path.exists():
        return None, None
    if contract.sha_scope == "file":
        digest_file = path if path.is_file() else resolve_adapter_weight_file(path)
        return (compute_file_sha256(digest_file), digest_file) if digest_file else (None, None)
    if contract.sha_scope == "directory_manifest" and path.is_dir():
        return compute_directory_manifest_sha256(path), path
    return None, None


def check_asset(contract: AssetContract, *, allow_missing: bool = True) -> AssetCheck:
    path = contract.expanded_path
    exists = path.exists()
    kind_ok = kind_matches(path, contract.path_kind) if exists else False
    if not exists:
        return AssetCheck(contract.name, contract.path_source, contract.path_kind, contract.expected_sha256, contract.sha_scope, False, False, False, None, None, None, "MISSING_ALLOWED" if allow_missing else "BLOCK_ASSET_PATH_MISSING", "asset path is not present in this environment")
    if not kind_ok:
        return AssetCheck(contract.name, contract.path_source, contract.path_kind, contract.expected_sha256, contract.sha_scope, True, False, False, None, None, None, "BLOCK_ASSET_KIND_MISMATCH", "asset exists but has wrong kind")
    if contract.expected_sha256 is None:
        return AssetCheck(contract.name, contract.path_source, contract.path_kind, None, contract.sha_scope, True, True, False, None, None, None, "SHA_NOT_REQUIRED", "expected SHA-256 is intentionally not required")
    if not _sha256_is_full(contract.expected_sha256):
        return AssetCheck(contract.name, contract.path_source, contract.path_kind, contract.expected_sha256, contract.sha_scope, True, True, False, None, None, None, "BLOCK_V3_SHA_CONTRACT_INVALID", "expected SHA-256 must be full lowercase 64-character digest")
    actual, digest_path = compute_sha_for_contract(contract)
    if actual is None:
        return AssetCheck(contract.name, contract.path_source, contract.path_kind, contract.expected_sha256, contract.sha_scope, True, True, False, None, None, None, "PARTIAL_DONE_V3_SHA_SCOPE_PENDING", "adapter weight file could not be resolved")
    match = actual == contract.expected_sha256
    resolved_digest_path = digest_path.name if digest_path else None
    return AssetCheck(contract.name, contract.path_source, contract.path_kind, contract.expected_sha256, contract.sha_scope, True, True, True, match, actual, resolved_digest_path, "PASS" if match else "BLOCK_V2_SHA_MISMATCH", "sha verified" if match else "sha mismatch")


def verify_asset_contracts(*, allow_missing: bool = True) -> dict[str, AssetCheck]:
    return {name: check_asset(contract, allow_missing=allow_missing) for name, contract in asset_contracts().items()}


def sha_mismatch_count(checks: dict[str, AssetCheck]) -> int:
    return sum(1 for check in checks.values() if check.status in {"BLOCK_V2_SHA_MISMATCH", "BLOCK_V3_SHA_MISMATCH"})


def load_sha_contract_v3(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def export_asset_checks(path: str | Path, *, allow_missing: bool = True) -> None:
    checks = verify_asset_contracts(allow_missing=allow_missing)
    payload = {name: asdict(check) for name, check in checks.items()}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
