from __future__ import annotations

import json
from pathlib import Path

from butler_pc_core.company_policy.vault import LocalEncryptedVault, VaultError

from .contracts import (
    CompanyProfileIndexEntry,
    CompanyProfileRuntime,
    ContractValidationError,
    make_index_entry,
    validate_index_entry_dict,
    validate_runtime_profile_dict,
)


class ProfileLoadError(RuntimeError):
    pass


class CompanyProfileStore:
    def __init__(self, root: Path | None = None, vault: LocalEncryptedVault | None = None) -> None:
        self.root = root or Path(".butler_company_profile_store")
        self.root.mkdir(parents=True, exist_ok=True)
        self.vault = vault or LocalEncryptedVault(root=self.root / "vault", key_path=self.root / "vault.key")
        self.index_path = self.root / "active_profile_ref.json"

    def save_profile(self, runtime: CompanyProfileRuntime) -> CompanyProfileIndexEntry:
        data = runtime.to_vault_dict()
        profile_ref, _vault_digest = self.vault.encrypt_json(
            "company_profile",
            runtime.profile_id,
            data,
            aad=runtime.profile_digest,
        )
        entry = make_index_entry(runtime=runtime, profile_ref=profile_ref)
        self.index_path.write_text(
            json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return entry

    def load_active_index(self) -> CompanyProfileIndexEntry | None:
        if not self.index_path.exists():
            return None
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            validate_index_entry_dict(data)
            return CompanyProfileIndexEntry(**data)
        except Exception as exc:
            raise ProfileLoadError("COMPANY_PROFILE_INDEX_LOAD_FAILED") from exc

    def load_active_profile(self) -> CompanyProfileRuntime | None:
        entry = self.load_active_index()
        if entry is None:
            return None
        try:
            data = self.vault.decrypt_json(entry.profile_ref, aad=entry.profile_digest)
            validate_runtime_profile_dict(data)
            runtime = CompanyProfileRuntime(**data)
            if runtime.profile_digest != entry.profile_digest:
                raise ProfileLoadError("COMPANY_PROFILE_DIGEST_MISMATCH")
            return runtime
        except (VaultError, ContractValidationError, TypeError) as exc:
            raise ProfileLoadError("COMPANY_PROFILE_LOAD_FAILED") from exc
