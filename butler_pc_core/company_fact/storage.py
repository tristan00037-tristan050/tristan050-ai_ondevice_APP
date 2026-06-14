from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler_pc_core.company_policy.admin_auth import verify_admin_context
from butler_pc_core.company_policy.contracts import AdminContext
from butler_pc_core.company_policy.vault import LocalEncryptedVault, VaultError

from .audit import CompanyFactAuditStore
from .contracts import (
    CompanyFactContractError,
    CompanyFactIndexEntry,
    CompanyFactVaultRecord,
    make_company_fact_record,
    make_index_entry,
    now_iso,
    validate_index_entry_dict,
    validate_vault_record_dict,
)


class CompanyFactLoadError(RuntimeError):
    pass


class CompanyFactStore:
    def __init__(
        self,
        root: Path | None = None,
        vault: LocalEncryptedVault | None = None,
        audit_store: CompanyFactAuditStore | None = None,
    ) -> None:
        self.root = root or Path(".butler_company_fact_store")
        self.root.mkdir(parents=True, exist_ok=True)
        self.vault = vault or LocalEncryptedVault(root=self.root / "vault", key_path=self.root / "vault.key")
        self.index_path = self.root / "company_facts_index.json"
        self.audit_store = audit_store or CompanyFactAuditStore(root=self.root)

    def _empty_index(self) -> dict[str, Any]:
        return {"schema_version": "company_fact.index_file.v1", "facts": {}}

    def _load_index_data(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return self._empty_index()
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if data.get("schema_version") != "company_fact.index_file.v1":
                raise CompanyFactLoadError("COMPANY_FACT_INDEX_SCHEMA_INVALID")
            if not isinstance(data.get("facts"), dict):
                raise CompanyFactLoadError("COMPANY_FACT_INDEX_FACTS_INVALID")
            for value in data["facts"].values():
                validate_index_entry_dict(value)
            return data
        except CompanyFactLoadError:
            raise
        except Exception as exc:
            raise CompanyFactLoadError("COMPANY_FACT_INDEX_LOAD_FAILED") from exc

    def _save_index_data(self, data: dict[str, Any]) -> None:
        self.index_path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def list_index_entries(self, *, status: str | None = None) -> list[CompanyFactIndexEntry]:
        data = self._load_index_data()
        entries = [CompanyFactIndexEntry(**value) for value in data["facts"].values()]
        if status is not None:
            entries = [entry for entry in entries if entry.status == status]
        return sorted(entries, key=lambda entry: entry.fact_id)

    def _write_record(self, record: CompanyFactVaultRecord, *, reason_code: str, actor_digest: str | None = None) -> tuple[CompanyFactIndexEntry, dict[str, Any]]:
        ref, _vault_digest = self.vault.encrypt_json(
            "company_facts",
            record.fact_id,
            record.to_vault_dict(),
            aad=record.fact_digest,
        )
        entry = make_index_entry(record=record, fact_ref=ref)
        data = self._load_index_data()
        data["facts"][entry.fact_id] = entry.to_dict()
        self._save_index_data(data)
        audit = self.audit_store.append(
            action=f"company_fact.{record.status.lower()}",
            fact_digest=record.fact_digest,
            actor_digest=actor_digest,
            reason_code=reason_code,
        )
        return entry, audit

    def save_candidate(
        self,
        *,
        category: str,
        question_patterns: list[str],
        keywords_required: list[str] | None,
        keywords_any: list[str] | None,
        answer_runtime_text: str,
        source: str,
        source_url: str | None = None,
        source_doc: str | None = None,
        verified_at: str | None = None,
        expires_at: str | None = None,
        confidence: float = 0.5,
    ) -> tuple[CompanyFactIndexEntry, dict[str, Any]]:
        record = make_company_fact_record(
            status="CANDIDATE",
            category=category,
            question_patterns=question_patterns,
            keywords_required=keywords_required,
            keywords_any=keywords_any,
            answer_runtime_text=answer_runtime_text,
            source=source,
            source_url=source_url,
            source_doc=source_doc,
            verified_at=verified_at,
            expires_at=expires_at,
            confidence=confidence,
        )
        return self._write_record(record, reason_code="CANDIDATE_SUBMITTED")

    def load_fact(self, fact_id: str) -> CompanyFactVaultRecord:
        data = self._load_index_data()
        entry_data = data["facts"].get(fact_id)
        if not isinstance(entry_data, dict):
            raise CompanyFactLoadError("COMPANY_FACT_NOT_FOUND")
        entry = CompanyFactIndexEntry(**entry_data)
        try:
            value = self.vault.decrypt_json(entry.fact_ref, aad=entry.fact_digest)
            validate_vault_record_dict(value)
            record = CompanyFactVaultRecord(**value)
            if record.fact_digest != entry.fact_digest:
                raise CompanyFactLoadError("COMPANY_FACT_DIGEST_MISMATCH")
            return record
        except (VaultError, CompanyFactContractError, TypeError) as exc:
            raise CompanyFactLoadError("COMPANY_FACT_LOAD_FAILED") from exc

    def approve_candidate(self, fact_id: str, admin: AdminContext) -> tuple[CompanyFactIndexEntry, dict[str, Any]]:
        verified_admin = verify_admin_context(admin, operation="approve_company_fact")
        current = self.load_fact(fact_id)
        if current.status != "CANDIDATE":
            raise CompanyFactContractError("COMPANY_FACT_APPROVE_REQUIRES_CANDIDATE")
        active = make_company_fact_record(
            status="ACTIVE",
            fact_id=current.fact_id,
            category=current.category,
            question_patterns=current.question_patterns,
            keywords_required=current.keywords_required,
            keywords_any=current.keywords_any,
            answer_runtime_text=current.answer_runtime_text,
            source=current.source,
            source_url=current.source_url,
            source_doc=current.source_doc,
            verified_at=current.verified_at,
            expires_at=current.expires_at,
            confidence=1.0,
            approved_by_digest=verified_admin.admin_id_digest,
            approved_at=now_iso(),
            previous_fact_digest=current.fact_digest,
        )
        return self._write_record(
            active,
            reason_code="CANDIDATE_APPROVED",
            actor_digest=verified_admin.admin_id_digest,
        )

    def deprecate_fact(self, fact_id: str, admin: AdminContext) -> tuple[CompanyFactIndexEntry, dict[str, Any]]:
        verified_admin = verify_admin_context(admin, operation="deprecate_company_fact")
        current = self.load_fact(fact_id)
        if current.status == "DEPRECATED":
            return self._write_record(
                current,
                reason_code="ALREADY_DEPRECATED",
                actor_digest=verified_admin.admin_id_digest,
            )
        deprecated = make_company_fact_record(
            status="DEPRECATED",
            fact_id=current.fact_id,
            category=current.category,
            question_patterns=current.question_patterns,
            keywords_required=current.keywords_required,
            keywords_any=current.keywords_any,
            answer_runtime_text=current.answer_runtime_text,
            source=current.source,
            source_url=current.source_url,
            source_doc=current.source_doc,
            verified_at=current.verified_at,
            expires_at=current.expires_at,
            confidence=0.0,
            approved_by_digest=current.approved_by_digest,
            approved_at=current.approved_at,
            previous_fact_digest=current.fact_digest,
        )
        return self._write_record(
            deprecated,
            reason_code="ACTIVE_DEPRECATED",
            actor_digest=verified_admin.admin_id_digest,
        )

    def load_active_facts(self) -> list[CompanyFactVaultRecord]:
        active: list[CompanyFactVaultRecord] = []
        for entry in self.list_index_entries(status="ACTIVE"):
            try:
                active.append(self.load_fact(entry.fact_id))
            except CompanyFactLoadError as exc:
                raise CompanyFactLoadError("COMPANY_FACT_ACTIVE_LOAD_FAILED") from exc
        return active
