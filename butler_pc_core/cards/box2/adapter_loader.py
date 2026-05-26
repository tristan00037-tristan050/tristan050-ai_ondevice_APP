from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal

DEFAULT_HANDOFF_ROOT = "~/Desktop/도우미폴더/넘겨줄도우미모델"

DEFAULT_BASE_MODEL_PATH = f"{DEFAULT_HANDOFF_ROOT}/Qwen3-1.7B"

DEFAULT_BUTLER_V3_LORA_PATH = (
    f"{DEFAULT_HANDOFF_ROOT}/butler-qwen3-1.7b-v3/lora_adapter"
)

DEFAULT_BUTLER_V3_GGUF_F16_PATH = (
    f"{DEFAULT_HANDOFF_ROOT}/butler-qwen3-1.7b-v3/butler-1.7b-v3-f16.gguf"
)

DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH = (
    f"{DEFAULT_HANDOFF_ROOT}/butler-qwen3-1.7b-v3/butler-1.7b-v3-q4_k_m.gguf"
)

DEFAULT_HELPER_3_PATH = (
    f"{DEFAULT_HANDOFF_ROOT}/box2b_v5_outputs/rewrite/adapter/box2b_v5_rewrite"
)

# v2 contract: sealed with the full 64-char file SHA of adapter_model.safetensors
# after user sealed sha_contract_v2.json with the same value. Scope: file.
BUTLER_V3_LORA_ADAPTER_SHA: str | None = (
    "ee35fe47c2421df18597dd9939a08b4ff3bf4e25b8766ba5d914060ccaedd284"
)

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
    def expanded_path(self) -> Path:
        return Path(self.path).expanduser()


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
    status: str
    reason: str


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
        rel = item.relative_to(directory).as_posix()
        yield rel, compute_file_sha256(item)


def compute_directory_manifest_sha256(directory: Path) -> str:
    """Return a deterministic digest over relative paths and file digests.

    This is not a tar/zip digest. It is a stable manifest digest designed to
    survive filesystem metadata changes while detecting content/path changes.
    """
    h = hashlib.sha256()
    for rel_path, file_sha in _iter_manifest_entries(directory):
        h.update(rel_path.encode("utf-8"))
        h.update(b"\0")
        h.update(file_sha.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def asset_contracts() -> dict[str, AssetContract]:
    return {
        "base_model": AssetContract(
            name="base_model",
            path=DEFAULT_BASE_MODEL_PATH,
            path_kind="directory",
            expected_sha256=None,
            sha_scope="unknown",
        ),
        "butler_v3_lora": AssetContract(
            name="butler_v3_lora",
            path=DEFAULT_BUTLER_V3_LORA_PATH,
            path_kind="directory",
            expected_sha256=BUTLER_V3_LORA_ADAPTER_SHA,
            sha_scope="file" if BUTLER_V3_LORA_ADAPTER_SHA is not None else "unknown",
        ),
        "butler_v3_gguf_f16": AssetContract(
            name="butler_v3_gguf_f16",
            path=DEFAULT_BUTLER_V3_GGUF_F16_PATH,
            path_kind="file",
            expected_sha256=BUTLER_V3_F16_GGUF_SHA,
            sha_scope="file",
        ),
        "butler_v3_gguf_q4_k_m": AssetContract(
            name="butler_v3_gguf_q4_k_m",
            path=DEFAULT_BUTLER_V3_GGUF_Q4_K_M_PATH,
            path_kind="file",
            expected_sha256=BUTLER_V3_Q4_K_M_GGUF_SHA,
            sha_scope="file",
        ),
        "helper_3": AssetContract(
            name="helper_3",
            path=DEFAULT_HELPER_3_PATH,
            path_kind="directory_or_file",
            expected_sha256=HELPER_3_REWRITE_ADAPTER_SHA,
            sha_scope="unknown",
        ),
    }


def kind_matches(path: Path, path_kind: PathKind) -> bool:
    if path_kind == "file":
        return path.is_file()
    if path_kind == "directory":
        return path.is_dir()
    if path_kind == "directory_or_file":
        return path.is_file() or path.is_dir()
    raise ValueError(f"unknown path kind: {path_kind}")


def compute_sha_for_contract(contract: AssetContract) -> str | None:
    path = contract.expanded_path
    if not path.exists():
        return None
    if contract.sha_scope == "file":
        if not path.is_file():
            return None
        return compute_file_sha256(path)
    if contract.sha_scope == "directory_manifest":
        if not path.is_dir():
            return None
        return compute_directory_manifest_sha256(path)
    return None


def check_asset(contract: AssetContract, *, allow_missing: bool = True) -> AssetCheck:
    path = contract.expanded_path
    exists = path.exists()
    kind_ok = kind_matches(path, contract.path_kind) if exists else False

    if not exists:
        status = "MISSING_ALLOWED" if allow_missing else "BLOCK_ASSET_PATH_MISSING"
        return AssetCheck(
            name=contract.name,
            path=contract.path,
            path_kind=contract.path_kind,
            expected_sha256=contract.expected_sha256,
            sha_scope=contract.sha_scope,
            exists=False,
            kind_ok=False,
            sha_checked=False,
            sha_match=None,
            actual_sha256=None,
            status=status,
            reason="asset path is not present in this environment",
        )

    if not kind_ok:
        return AssetCheck(
            name=contract.name,
            path=contract.path,
            path_kind=contract.path_kind,
            expected_sha256=contract.expected_sha256,
            sha_scope=contract.sha_scope,
            exists=True,
            kind_ok=False,
            sha_checked=False,
            sha_match=None,
            actual_sha256=None,
            status="BLOCK_ASSET_KIND_MISMATCH",
            reason="asset exists but is not the required file/directory kind",
        )

    if contract.expected_sha256 is None:
        return AssetCheck(
            name=contract.name,
            path=contract.path,
            path_kind=contract.path_kind,
            expected_sha256=None,
            sha_scope=contract.sha_scope,
            exists=True,
            kind_ok=True,
            sha_checked=False,
            sha_match=None,
            actual_sha256=None,
            status="PARTIAL_DONE_V2_LORA_SHA_SCOPE_PENDING" if contract.name == "butler_v3_lora" else "SHA_NOT_REQUIRED",
            reason="expected SHA-256 is intentionally not sealed in this package",
        )

    if not _sha256_is_full(contract.expected_sha256):
        return AssetCheck(
            name=contract.name,
            path=contract.path,
            path_kind=contract.path_kind,
            expected_sha256=contract.expected_sha256,
            sha_scope=contract.sha_scope,
            exists=True,
            kind_ok=True,
            sha_checked=False,
            sha_match=None,
            actual_sha256=None,
            status="BLOCK_V2_SHA_CONTRACT_INVALID",
            reason="expected SHA-256 must be a full lowercase 64-character digest",
        )

    actual = compute_sha_for_contract(contract)
    if actual is None:
        return AssetCheck(
            name=contract.name,
            path=contract.path,
            path_kind=contract.path_kind,
            expected_sha256=contract.expected_sha256,
            sha_scope=contract.sha_scope,
            exists=True,
            kind_ok=True,
            sha_checked=False,
            sha_match=None,
            actual_sha256=None,
            status="PARTIAL_DONE_V2_SHA_SCOPE_PENDING",
            reason="sha_scope is unknown or incompatible with the existing path",
        )

    match = actual == contract.expected_sha256
    return AssetCheck(
        name=contract.name,
        path=contract.path,
        path_kind=contract.path_kind,
        expected_sha256=contract.expected_sha256,
        sha_scope=contract.sha_scope,
        exists=True,
        kind_ok=True,
        sha_checked=True,
        sha_match=match,
        actual_sha256=actual,
        status="PASS" if match else "BLOCK_V2_SHA_MISMATCH",
        reason="sha verified" if match else "sha mismatch",
    )


def verify_asset_contracts(*, allow_missing: bool = True) -> dict[str, AssetCheck]:
    return {name: check_asset(contract, allow_missing=allow_missing) for name, contract in asset_contracts().items()}


def sha_mismatch_count(checks: dict[str, AssetCheck]) -> int:
    return sum(1 for check in checks.values() if check.status == "BLOCK_V2_SHA_MISMATCH")


def load_sha_contract_v2(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def export_asset_checks(path: str | Path, *, allow_missing: bool = True) -> None:
    checks = verify_asset_contracts(allow_missing=allow_missing)
    payload = {name: asdict(check) for name, check in checks.items()}
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
