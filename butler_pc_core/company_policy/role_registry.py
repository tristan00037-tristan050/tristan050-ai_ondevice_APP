from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback keeps tests importable.
    fcntl = None  # type: ignore[assignment]

from .contracts import AdminContext, ROLE_VALUES, ContractValidationError, require_digest
from .role_registry_audit import RoleRegistryAuditLoadError, RoleRegistryAuditStore
from .role_registry_contracts import (
    ROLE_REGISTRY_INDEX_FILE_SCHEMA,
    RoleRegistryContractError,
    RoleRegistryEntry,
    RoleRegistryIndexEntry,
    make_role_registry_entry,
    make_role_registry_index_entry,
    validate_role_registry_index_entry_dict,
)
from .vault import LocalEncryptedVault, VaultError


class RoleRegistryLoadError(RuntimeError):
    pass


class RoleRegistryMutationError(RuntimeError):
    pass


class RoleRegistryStore:
    def __init__(
        self,
        root: Path | None = None,
        vault: LocalEncryptedVault | None = None,
        audit_store: RoleRegistryAuditStore | None = None,
    ) -> None:
        self.root = root or Path(".butler_role_registry_store")
        self.root.mkdir(parents=True, exist_ok=True)
        self.vault = vault or LocalEncryptedVault(root=self.root / "vault", key_path=self.root / "vault.key")
        self.audit_store = audit_store or RoleRegistryAuditStore(root=self.root)
        self.index_path = self.root / "role_registry_index.json"
        self.lock_path = self.root / "role_registry.lock"
        self._thread_lock = threading.RLock()

    @contextlib.contextmanager
    def _registry_lock(self):
        with self._thread_lock:
            if fcntl is None:
                yield
                return
            with self.lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _empty_index(self) -> dict[str, Any]:
        return {"schema_version": ROLE_REGISTRY_INDEX_FILE_SCHEMA, "members": {}}

    def _load_index_data_locked(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return self._empty_index()
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if data.get("schema_version") != ROLE_REGISTRY_INDEX_FILE_SCHEMA:
                raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_INDEX_SCHEMA_INVALID")
            if not isinstance(data.get("members"), dict):
                raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_INDEX_MEMBERS_INVALID")
            for key, value in data["members"].items():
                require_digest(key, "target_admin_id")
                validate_role_registry_index_entry_dict(value)
                if value["target_admin_id_digest"] != key:
                    raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_INDEX_KEY_MISMATCH")
            return data
        except RoleRegistryLoadError:
            raise
        except Exception as exc:
            raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_LOAD_FAILED") from exc

    def _save_index_data_locked(self, data: dict[str, Any]) -> None:
        temp_path = self.index_path.with_name(self.index_path.name + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, self.index_path)

    def _load_entry_locked(self, index_entry: RoleRegistryIndexEntry) -> RoleRegistryEntry:
        try:
            value = self.vault.decrypt_json(index_entry.entry_ref, aad=index_entry.entry_digest)
            entry = RoleRegistryEntry(**value)
            entry.to_vault_dict()
            if entry.entry_digest != index_entry.entry_digest:
                raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_ENTRY_DIGEST_MISMATCH")
            if entry.target_admin_id_digest != index_entry.target_admin_id_digest:
                raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_ENTRY_TARGET_MISMATCH")
            if entry.role != index_entry.role or entry.status != index_entry.status:
                raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_INDEX_ENTRY_MISMATCH")
            return entry
        except (VaultError, RoleRegistryContractError, ContractValidationError, TypeError) as exc:
            raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_LOAD_FAILED") from exc

    def _load_entries_locked(self, data: dict[str, Any]) -> dict[str, RoleRegistryEntry]:
        entries: dict[str, RoleRegistryEntry] = {}
        for key, value in data["members"].items():
            index_entry = RoleRegistryIndexEntry(**value)
            entries[key] = self._load_entry_locked(index_entry)
        return entries

    def _audit_health_locked(self, data: dict[str, Any]) -> None:
        try:
            members = data.get("members")
            audit_required = isinstance(members, dict) and bool(members)
            if audit_required:
                log_path = self.audit_store.log_path
                head_path = self.audit_store.head_path
                if log_path is None or head_path is None or not log_path.exists() or not head_path.exists():
                    raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_MISSING")
            self.audit_store._load_from_disk()
            if audit_required and not self.audit_store.records:
                raise RoleRegistryAuditLoadError("ROLE_REGISTRY_AUDIT_EMPTY_FOR_POPULATED_REGISTRY")
        except RoleRegistryAuditLoadError as exc:
            raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_LOAD_FAILED") from exc

    @staticmethod
    def _active_admin_count(entries: dict[str, RoleRegistryEntry]) -> int:
        return sum(1 for entry in entries.values() if entry.status == "ACTIVE" and entry.role == "admin")

    def is_empty(self) -> bool:
        with self._registry_lock():
            data = self._load_index_data_locked()
            self._audit_health_locked(data)
            return not any(value.get("status") == "ACTIVE" for value in data["members"].values())

    def lookup_active(self, target_admin_id_digest: str) -> RoleRegistryEntry | None:
        require_digest(target_admin_id_digest, "target_admin_id")
        with self._registry_lock():
            data = self._load_index_data_locked()
            self._audit_health_locked(data)
            entry_data = data["members"].get(target_admin_id_digest)
            if not isinstance(entry_data, dict):
                return None
            entry = self._load_entry_locked(RoleRegistryIndexEntry(**entry_data))
            if entry.status != "ACTIVE":
                return None
            return entry

    def status_summary(self) -> dict[str, Any]:
        with self._registry_lock():
            data = self._load_index_data_locked()
            self._audit_health_locked(data)
            entries = self._load_entries_locked(data)
            active_entries = [entry for entry in entries.values() if entry.status == "ACTIVE"]
            return {
                "initialized": bool(active_entries),
                "active_member_count": len(active_entries),
                "active_admin_count": self._active_admin_count(entries),
                "audit_head_valid": True,
                "raw_text_logged": False,
                "external_send_zero": True,
            }

    def _commit_entry_locked(
        self,
        data: dict[str, Any],
        entry: RoleRegistryEntry,
        *,
        action: str,
        actor_digest: str,
        reason_code: str,
    ) -> tuple[RoleRegistryIndexEntry, dict[str, Any]]:
        item_id = "entry-" + entry.entry_digest.split(":", 1)[1]
        entry_ref, _vault_digest = self.vault.encrypt_json(
            "role_registry",
            item_id,
            entry.to_vault_dict(),
            aad=entry.entry_digest,
        )
        index_entry = make_role_registry_index_entry(entry=entry, entry_ref=entry_ref)
        data["members"][entry.target_admin_id_digest] = index_entry.to_dict()
        self._save_index_data_locked(data)
        try:
            audit = self.audit_store.append(
                action=action,
                target_admin_id_digest=entry.target_admin_id_digest,
                actor_digest=actor_digest,
                entry_digest=entry.entry_digest,
                reason_code=reason_code,
            )
        except RoleRegistryAuditLoadError as exc:
            raise RoleRegistryLoadError("ADMIN_ROLE_REGISTRY_LOAD_FAILED") from exc
        return index_entry, audit

    def bootstrap_self_admin(self, actor: AdminContext) -> tuple[RoleRegistryIndexEntry, dict[str, Any]]:
        if actor.role != "admin":
            raise RoleRegistryMutationError("ADMIN_ROLE_REGISTRY_ROLE_INVALID")
        require_digest(actor.admin_id_digest, "actor")
        with self._registry_lock():
            data = self._load_index_data_locked()
            self._audit_health_locked(data)
            entries = self._load_entries_locked(data)
            if any(entry.status == "ACTIVE" for entry in entries.values()):
                raise RoleRegistryMutationError("ADMIN_ROLE_REGISTRY_ALREADY_INITIALIZED")
            entry = make_role_registry_entry(
                target_admin_id_digest=actor.admin_id_digest,
                role="admin",
                status="ACTIVE",
                registered_by_digest=actor.admin_id_digest,
                updated_by_digest=actor.admin_id_digest,
                version=1,
            )
            return self._commit_entry_locked(
                data,
                entry,
                action="role_registry.bootstrap_self_admin",
                actor_digest=actor.admin_id_digest,
                reason_code="INITIAL_SETUP_SELF_ADMIN",
            )

    def upsert_member(
        self,
        *,
        actor: AdminContext,
        target_admin_id_digest: str,
        role: str,
    ) -> tuple[RoleRegistryIndexEntry, dict[str, Any]]:
        require_digest(actor.admin_id_digest, "actor")
        require_digest(target_admin_id_digest, "target_admin_id")
        if role not in ROLE_VALUES:
            raise RoleRegistryMutationError("ADMIN_ROLE_REGISTRY_ROLE_INVALID")
        with self._registry_lock():
            data = self._load_index_data_locked()
            self._audit_health_locked(data)
            entries = self._load_entries_locked(data)
            current = entries.get(target_admin_id_digest)
            version = 1 if current is None else current.version + 1
            previous = None if current is None else current.entry_digest
            registered_by = actor.admin_id_digest if current is None else current.registered_by_digest
            entry = make_role_registry_entry(
                target_admin_id_digest=target_admin_id_digest,
                role=role,
                status="ACTIVE",
                registered_by_digest=registered_by,
                updated_by_digest=actor.admin_id_digest,
                version=version,
                previous_entry_digest=previous,
            )
            projected = dict(entries)
            projected[target_admin_id_digest] = entry
            if self._active_admin_count(projected) == 0:
                raise RoleRegistryMutationError("ADMIN_ROLE_REGISTRY_LAST_ADMIN")
            return self._commit_entry_locked(
                data,
                entry,
                action="role_registry.upsert",
                actor_digest=actor.admin_id_digest,
                reason_code="ROLE_REGISTRY_MEMBER_UPSERTED",
            )

    def remove_member(
        self,
        *,
        actor: AdminContext,
        target_admin_id_digest: str,
    ) -> tuple[RoleRegistryIndexEntry, dict[str, Any]]:
        require_digest(actor.admin_id_digest, "actor")
        require_digest(target_admin_id_digest, "target_admin_id")
        with self._registry_lock():
            data = self._load_index_data_locked()
            self._audit_health_locked(data)
            entries = self._load_entries_locked(data)
            current = entries.get(target_admin_id_digest)
            if current is None:
                raise RoleRegistryMutationError("ADMIN_ROLE_REGISTRY_TARGET_NOT_FOUND")
            entry = make_role_registry_entry(
                target_admin_id_digest=target_admin_id_digest,
                role=current.role,
                status="REMOVED",
                registered_by_digest=current.registered_by_digest,
                updated_by_digest=actor.admin_id_digest,
                version=current.version + 1,
                previous_entry_digest=current.entry_digest,
            )
            projected = dict(entries)
            projected[target_admin_id_digest] = entry
            if self._active_admin_count(projected) == 0:
                raise RoleRegistryMutationError("ADMIN_ROLE_REGISTRY_LAST_ADMIN")
            return self._commit_entry_locked(
                data,
                entry,
                action="role_registry.remove",
                actor_digest=actor.admin_id_digest,
                reason_code="ROLE_REGISTRY_MEMBER_REMOVED",
            )


_DEFAULT_ROLE_REGISTRY_STORE: RoleRegistryStore | None = None


def get_default_role_registry_store() -> RoleRegistryStore:
    global _DEFAULT_ROLE_REGISTRY_STORE
    if _DEFAULT_ROLE_REGISTRY_STORE is None:
        _DEFAULT_ROLE_REGISTRY_STORE = RoleRegistryStore()
    return _DEFAULT_ROLE_REGISTRY_STORE
