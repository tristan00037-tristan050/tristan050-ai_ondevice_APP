from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler_pc_core.app_data import product_data_root
from butler_pc_core.strict_json import load_strict_bytes
from butler_pc_core.company_policy.admin_auth import verify_admin_context
from butler_pc_core.company_policy.contracts import AdminContext, stable_json_digest
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
from .known_bad import (
    DEPRECATE_REASON_CODES,
    KnownBadContractError,
    KnownBadIndexEntry,
    KnownBadVaultEntry,
    build_known_bad_vault_entry,
    make_known_bad_index_entry,
    make_known_bad_override_record,
    match_known_bad_candidate,
    validate_known_bad_index_entry,
    validate_known_bad_override_record,
    validate_known_bad_vault_entry,
)


class CompanyFactLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompanyFactCapabilitySummary:
    active_count: int
    active_fact_digests: tuple[str, ...]
    revision: str


class CompanyFactStore:
    def __init__(
        self,
        root: Path | None = None,
        vault: LocalEncryptedVault | None = None,
        audit_store: CompanyFactAuditStore | None = None,
    ) -> None:
        self.root = root or product_data_root(
            "company-facts",
            legacy_name=".butler_company_fact_store",
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.vault = vault or LocalEncryptedVault(root=self.root / "vault", key_path=self.root / "vault.key")
        self.index_path = self.root / "company_facts_index.json"
        self.known_bad_index_path = self.root / "company_fact_known_bad_index.json"
        self.known_bad_override_path = self.root / "company_fact_known_bad_overrides.json"
        self.audit_store = audit_store or CompanyFactAuditStore(root=self.root)
        self._mutation_lock = threading.RLock()

    def _empty_index(self) -> dict[str, Any]:
        return {"schema_version": "company_fact.index_file.v1", "facts": {}}

    def _load_index_data(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return self._empty_index()
        try:
            data = load_strict_bytes(self.index_path.read_bytes(), allow_float=True)
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

    def _empty_known_bad_index(self) -> dict[str, Any]:
        return {"schema_version": "company_fact.known_bad_index_file.v1", "entries": {}}

    def _load_known_bad_index_data(self) -> dict[str, Any]:
        if not self.known_bad_index_path.exists():
            return self._empty_known_bad_index()
        try:
            data = load_strict_bytes(
                self.known_bad_index_path.read_bytes(),
                allow_float=True,
            )
            if data.get("schema_version") != "company_fact.known_bad_index_file.v1":
                raise CompanyFactLoadError("KNOWN_BAD_INDEX_SCHEMA_INVALID")
            if not isinstance(data.get("entries"), dict):
                raise CompanyFactLoadError("KNOWN_BAD_INDEX_ENTRIES_INVALID")
            for value in data["entries"].values():
                validate_known_bad_index_entry(value)
            return data
        except CompanyFactLoadError:
            raise
        except KnownBadContractError as exc:
            raise CompanyFactLoadError("KNOWN_BAD_INDEX_LOAD_FAILED") from exc
        except Exception as exc:
            raise CompanyFactLoadError("KNOWN_BAD_INDEX_LOAD_FAILED") from exc

    def _save_known_bad_index_data(self, data: dict[str, Any]) -> None:
        self.known_bad_index_path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def _load_override_data(self) -> dict[str, Any]:
        if not self.known_bad_override_path.exists():
            return {"schema_version": "company_fact.known_bad_override_file.v1", "overrides": {}}
        try:
            data = load_strict_bytes(
                self.known_bad_override_path.read_bytes(),
                allow_float=True,
            )
            if data.get("schema_version") != "company_fact.known_bad_override_file.v1":
                raise CompanyFactLoadError("KNOWN_BAD_OVERRIDE_SCHEMA_INVALID")
            if not isinstance(data.get("overrides"), dict):
                raise CompanyFactLoadError("KNOWN_BAD_OVERRIDE_MAP_INVALID")
            for value in data["overrides"].values():
                validate_known_bad_override_record(value)
            return data
        except CompanyFactLoadError:
            raise
        except KnownBadContractError as exc:
            raise CompanyFactLoadError("KNOWN_BAD_OVERRIDE_LOAD_FAILED") from exc
        except Exception as exc:
            raise CompanyFactLoadError("KNOWN_BAD_OVERRIDE_LOAD_FAILED") from exc

    def _save_override_data(self, data: dict[str, Any]) -> None:
        for value in data.get("overrides", {}).values():
            validate_known_bad_override_record(value)
        self.known_bad_override_path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def load_known_bad_entries(self) -> list[KnownBadVaultEntry]:
        data = self._load_known_bad_index_data()
        entries: list[KnownBadVaultEntry] = []
        for entry_data in data["entries"].values():
            index_entry = KnownBadIndexEntry(**entry_data)
            try:
                value = self.vault.decrypt_json(index_entry.known_bad_ref, aad=index_entry.bad_entry_digest)
                validate_known_bad_vault_entry(value)
                entries.append(KnownBadVaultEntry(**value))
            except (VaultError, KnownBadContractError, TypeError) as exc:
                raise CompanyFactLoadError("KNOWN_BAD_ENTRY_LOAD_FAILED") from exc
        return entries

    def _candidate_has_known_bad_override(
        self,
        record: CompanyFactVaultRecord,
        *,
        bad_entry_id: str | None = None,
        bad_fact_digest: str | None = None,
    ) -> bool:
        try:
            data = self._load_override_data()
        except CompanyFactLoadError:
            # Drifted overrides must never clear known_bad_suspected. The loader
            # remains fail-closed for direct callers, while candidate approval
            # treats malformed override state as no usable override.
            return False
        value = data["overrides"].get(record.fact_id)
        if value is None:
            return False
        validate_known_bad_override_record(value)
        if value.get("status") != "ACTIVE":
            return False
        if value.get("fact_id") != record.fact_id:
            raise CompanyFactLoadError("KNOWN_BAD_OVERRIDE_FACT_ID_MISMATCH")
        if value.get("candidate_fact_digest") != record.fact_digest:
            return False
        if bad_entry_id is not None and value.get("bad_entry_id") != bad_entry_id:
            raise CompanyFactLoadError("KNOWN_BAD_OVERRIDE_BAD_ENTRY_MISMATCH")
        if bad_fact_digest is not None and value.get("bad_fact_digest") != bad_fact_digest:
            raise CompanyFactLoadError("KNOWN_BAD_OVERRIDE_BAD_FACT_DIGEST_MISMATCH")
        return True

    def known_bad_flags_for_candidate(self, record: CompanyFactVaultRecord) -> dict[str, Any]:
        # matcher는 핵심어/패턴 유사만 본다(키워드/패턴 매칭 한정, 뜻 단정 금지).
        match = match_known_bad_candidate(record, self.load_known_bad_entries())
        override_active = self._candidate_has_known_bad_override(
            record,
            bad_entry_id=(match.bad_entry_id if match else None),
            bad_fact_digest=(match.bad_fact_digest if match else None),
        )
        suspected = match is not None and not override_active
        return {
            "known_bad_suspected": suspected,
            "override_available": suspected,
            "override_active": override_active,
            "match_score": match.score if match else None,
            "matched_keywords_count": match.matched_keywords_count if match else 0,
            "matched_pattern_digest": match.matched_pattern_digest if match else None,
            "bad_entry_id": match.bad_entry_id if match else None,
            "bad_fact_digest": match.bad_fact_digest if match else None,
            "raw_text_logged": False,
            "external_send_zero": True,
        }

    def register_known_bad(self, record: CompanyFactVaultRecord, *, actor_digest: str) -> tuple[KnownBadIndexEntry, dict[str, Any]]:
        known_bad = build_known_bad_vault_entry(record=record, actor_digest=actor_digest, created_at=now_iso())
        ref, _digest = self.vault.encrypt_json(
            "company_fact_known_bad",
            known_bad.bad_entry_id,
            known_bad.to_vault_dict(),
            aad=known_bad.bad_entry_digest,
        )
        index_entry = make_known_bad_index_entry(entry=known_bad, known_bad_ref=ref)
        data = self._load_known_bad_index_data()
        data["entries"][index_entry.bad_entry_id] = index_entry.to_dict()
        self._save_known_bad_index_data(data)
        audit = self.audit_store.append(
            action="company_fact.known_bad_registered",
            fact_digest=known_bad.bad_entry_digest,
            actor_digest=actor_digest,
            reason_code="WRONG",
        )
        return index_entry, audit

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
        flags = self.known_bad_flags_for_candidate(current)
        if flags["known_bad_suspected"]:
            raise CompanyFactContractError("KNOWN_BAD_APPROVAL_BLOCKED")
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

    def deprecate_fact(self, fact_id: str, admin: AdminContext, *, reason_code: str = "MANUAL_DEPRECATED") -> tuple[CompanyFactIndexEntry, dict[str, Any]]:
        if reason_code not in DEPRECATE_REASON_CODES:
            raise CompanyFactContractError("DEPRECATE_REASON_CODE_INVALID")
        verified_admin = verify_admin_context(admin, operation="deprecate_company_fact")
        # 락은 load_fact 부터 _write_record + (WRONG 시) register_known_bad 까지 임계영역 전체를 감싼다.
        with self._mutation_lock:
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
            entry, audit = self._write_record(
                deprecated,
                reason_code=reason_code,
                actor_digest=verified_admin.admin_id_digest,
            )
            # WRONG deprecate만 known-bad를 등록한다. SUPERSEDED/MANUAL_DEPRECATED는 등록하지 않는다.
            if reason_code == "WRONG":
                self.register_known_bad(current, actor_digest=verified_admin.admin_id_digest)
            return entry, audit

    def override_known_bad_candidate(self, fact_id: str, admin: AdminContext) -> dict[str, Any]:
        verified_admin = verify_admin_context(admin, operation="override_known_bad_company_fact")
        current = self.load_fact(fact_id)
        if current.status != "CANDIDATE":
            raise CompanyFactContractError("KNOWN_BAD_OVERRIDE_REQUIRES_CANDIDATE")
        flags = self.known_bad_flags_for_candidate(current)
        if not flags["bad_entry_id"]:
            raise CompanyFactContractError("KNOWN_BAD_OVERRIDE_MATCH_NOT_FOUND")
        data = self._load_override_data()
        override = make_known_bad_override_record(
            fact_id=fact_id,
            candidate_fact_digest=current.fact_digest,
            bad_entry_id=flags["bad_entry_id"],
            bad_fact_digest=flags["bad_fact_digest"],
            approved_by_digest=verified_admin.admin_id_digest,
            approved_at=now_iso(),
        )
        data["overrides"][fact_id] = override.to_dict()
        self._save_override_data(data)
        audit = self.audit_store.append(
            action="company_fact.known_bad_override",
            fact_digest=current.fact_digest,
            actor_digest=verified_admin.admin_id_digest,
            reason_code="KNOWN_BAD_OVERRIDE_APPROVED",
        )
        return {"audit_ref": audit["audit_id"], **data["overrides"][fact_id]}

    def supersede_fact(self, fact_id: str, replacement: dict[str, Any], admin: AdminContext) -> dict[str, Any]:
        verified_admin = verify_admin_context(admin, operation="supersede_company_fact")
        with self._mutation_lock:
            current = self.load_fact(fact_id)
            if current.status != "ACTIVE":
                raise CompanyFactContractError("SUPERSEDE_REQUIRES_ACTIVE")
            replacement_record = make_company_fact_record(
                status="ACTIVE",
                category=replacement.get("category", current.category),
                question_patterns=replacement.get("question_patterns", current.question_patterns),
                keywords_required=replacement.get("keywords_required", current.keywords_required),
                keywords_any=replacement.get("keywords_any", current.keywords_any),
                answer_runtime_text=replacement.get("answer_runtime_text", current.answer_runtime_text),
                source=replacement.get("source", current.source),
                source_url=replacement.get("source_url", current.source_url),
                source_doc=replacement.get("source_doc", current.source_doc),
                verified_at=replacement.get("verified_at", current.verified_at),
                expires_at=replacement.get("expires_at", current.expires_at),
                confidence=1.0,
                approved_by_digest=verified_admin.admin_id_digest,
                approved_at=now_iso(),
                previous_fact_digest=current.fact_digest,
            )
            old_deprecated = make_company_fact_record(
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
            # 롤백 한계(직접성): 실패 시 index 스냅샷만 복원한다. 이미 기록된 vault 항목은
            # index에서 참조되지 않아 노출/서빙되지 않지만 물리적으로 잔존할 수 있고, audit 로그는
            # append-only(변조 탐지)라 시도 기록이 남을 수 있다. 본 한계는 PR에 명시한다.
            old_index_snapshot = self._load_index_data()
            try:
                old_entry, old_audit = self._write_record(old_deprecated, reason_code="SUPERSEDED", actor_digest=verified_admin.admin_id_digest)
                new_entry, new_audit = self._write_record(replacement_record, reason_code="SUPERSEDE_REPLACEMENT_ACTIVE", actor_digest=verified_admin.admin_id_digest)
            except Exception:
                self._save_index_data(old_index_snapshot)
                raise
        return {
            "schema_version": "company_fact.supersede.result.v1",
            "old_fact_id": old_entry.fact_id,
            "old_status": old_entry.status,
            "old_fact_digest": old_entry.fact_digest,
            "new_fact_id": new_entry.fact_id,
            "new_status": new_entry.status,
            "new_fact_digest": new_entry.fact_digest,
            "previous_fact_digest": current.fact_digest,
            "audit_refs": [old_audit["audit_id"], new_audit["audit_id"]],
            "raw_text_logged": False,
            "external_send_zero": True,
        }

    def load_active_facts(self) -> list[CompanyFactVaultRecord]:
        active: list[CompanyFactVaultRecord] = []
        for entry in self.list_index_entries(status="ACTIVE"):
            try:
                active.append(self.load_fact(entry.fact_id))
            except CompanyFactLoadError as exc:
                raise CompanyFactLoadError("COMPANY_FACT_ACTIVE_LOAD_FAILED") from exc
        return active

    def capability_summary(self) -> CompanyFactCapabilitySummary:
        # Validate every index record, every ACTIVE vault record, known-bad
        # records and overrides. A malformed side record cannot be skipped to
        # manufacture a positive capability.
        self._load_index_data()
        self.load_known_bad_entries()
        self._load_override_data()
        active = self.load_active_facts()
        for record in active:
            if self.known_bad_flags_for_candidate(record)["known_bad_suspected"]:
                raise CompanyFactLoadError("COMPANY_FACT_ACTIVE_KNOWN_BAD")
        digests = tuple(sorted(record.fact_digest for record in active))
        revision = stable_json_digest(
            {
                "schema_version": 1,
                "active_fact_digests": digests,
            }
        ).removeprefix("sha256:")
        return CompanyFactCapabilitySummary(
            active_count=len(active),
            active_fact_digests=digests,
            revision=revision,
        )
