from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler_pc_core.app_data import product_data_root

from .admin_auth import verify_admin_context
from .audit import GLOBAL_ADMIN_AUDIT_STORE, build_admin_audit_record
from .contracts import (
    AccessRule,
    AdminContext,
    CompanyFormat,
    CompanyPolicy,
    compute_format_digest,
    compute_policy_digest,
    make_company_format,
    make_company_policy,
    sha256_text,
    stable_json_digest,
    validate_company_format_dict,
    validate_company_policy_dict,
)
from .vault import LocalEncryptedVault, VaultError


class PolicyLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class PolicyCapabilitySummary:
    active_count: int
    active_policy_digest: str | None
    revision: str


class PolicyStore:
    def __init__(self, root: Path | None = None, vault: LocalEncryptedVault | None = None) -> None:
        self.root = root or product_data_root(
            "company-policy",
            legacy_name=".butler_policy_store",
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.vault = vault or LocalEncryptedVault(root=self.root / "vault", key_path=self.root / "vault.key")
        self.index_path = self.root / "active_policy_ref.json"

    def save_policy(self, policy: CompanyPolicy, admin: AdminContext, *, reason_code: str = "POLICY_REGISTERED") -> dict[str, Any]:
        verify_admin_context(admin, operation="save_policy")
        data = policy.to_dict()
        ref, digest = self.vault.encrypt_json("policies", policy.policy_id, data, aad=policy.policy_digest)
        self.index_path.write_text(json.dumps({"active_policy_ref": ref, "policy_digest": policy.policy_digest}, sort_keys=True), encoding="utf-8")
        return GLOBAL_ADMIN_AUDIT_STORE.append(
            build_admin_audit_record(
                action="company_policy.save",
                admin_id_digest=admin.admin_id_digest,
                object_digest=policy.policy_digest,
                extra_digest=digest,
                reason_code=reason_code,
            )
        )

    def load_active_policy(self) -> CompanyPolicy | None:
        if not self.index_path.exists():
            return None
        try:
            idx = json.loads(self.index_path.read_text(encoding="utf-8"))
            data = self.vault.decrypt_json(idx["active_policy_ref"], aad=idx["policy_digest"])
            validate_company_policy_dict(data)
            if data["policy_digest"] != compute_policy_digest(data):
                raise PolicyLoadError("POLICY_DIGEST_MISMATCH")
            rules = [AccessRule(**rule) for rule in data["access_rules"]]
            return CompanyPolicy(
                schema_version="company_policy.v1",
                policy_id=data["policy_id"],
                version=data["version"],
                status=data["status"],
                default_action=data["default_action"],
                doc_grades=data["doc_grades"],
                access_rules=rules,
                external_send_rules=data["external_send_rules"],
                masking_engine_verified=data["masking_engine_verified"],
                effective_from=data["effective_from"],
                expires_at=data["expires_at"],
                registered_by_digest=data["registered_by_digest"],
                previous_policy_digest=data["previous_policy_digest"],
                policy_digest=data["policy_digest"],
            )
        except Exception as exc:
            raise PolicyLoadError("POLICY_LOAD_FAILED") from exc

    def capability_summary(self) -> PolicyCapabilitySummary:
        policy = self.load_active_policy()
        active = policy is not None and policy.status == "ACTIVE"
        digest = policy.policy_digest if active else None
        revision = stable_json_digest(
            {
                "schema_version": 1,
                "active_count": int(active),
                "active_policy_digest": digest,
            }
        ).removeprefix("sha256:")
        return PolicyCapabilitySummary(
            active_count=int(active),
            active_policy_digest=digest,
            revision=revision,
        )


class CompanyFormatStore:
    def __init__(self, root: Path | None = None, vault: LocalEncryptedVault | None = None) -> None:
        self.root = root or product_data_root(
            "company-formats",
            legacy_name=".butler_format_store",
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.vault = vault or LocalEncryptedVault(root=self.root / "vault", key_path=self.root / "vault.key")
        self.index_path = self.root / "formats_index.json"

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"formats": {}}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: dict[str, Any]) -> None:
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    def register_format(
        self,
        *,
        template_runtime_text: str,
        format_kind: str,
        title_runtime_text: str,
        language: str,
        dept_digest: str,
        admin: AdminContext,
    ) -> tuple[CompanyFormat, dict[str, Any]]:
        verify_admin_context(admin, operation="register_format")
        template_digest = sha256_text(template_runtime_text)
        title_digest = sha256_text(title_runtime_text)
        # Store the raw template encrypted only inside the device-local vault.
        template_ref, vault_digest = self.vault.encrypt_json(
            "formats/templates",
            "template-" + template_digest.split(":", 1)[1][:24],
            {"template_runtime_text": template_runtime_text},
            aad=template_digest,
        )
        fmt = make_company_format(
            format_kind=format_kind,
            template_ref=template_ref,
            template_digest=template_digest,
            metadata={"title_digest": title_digest, "language": language, "dept_digest": dept_digest},
            registered_by_digest=admin.admin_id_digest,
        )
        idx = self._load_index()
        idx["formats"][fmt.format_id] = fmt.to_dict()
        self._save_index(idx)
        audit = GLOBAL_ADMIN_AUDIT_STORE.append(
            build_admin_audit_record(
                action="company_format.register",
                admin_id_digest=admin.admin_id_digest,
                object_digest=fmt.format_digest,
                extra_digest=vault_digest,
                reason_code="FORMAT_REGISTERED_ENCRYPTED",
            )
        )
        return fmt, audit

    def get_format(self, format_id: str) -> CompanyFormat | None:
        idx = self._load_index()
        data = idx.get("formats", {}).get(format_id)
        if not isinstance(data, dict):
            return None
        validate_company_format_dict(data)
        if data["format_digest"] != compute_format_digest(data):
            return None
        return CompanyFormat(**data)

    def load_template_runtime_only(self, company_format: CompanyFormat) -> str:
        # The returned text must remain in process memory and must not be passed to audit/log.
        value = self.vault.decrypt_json(company_format.template_ref, aad=company_format.template_digest)
        text = value.get("template_runtime_text")
        if not isinstance(text, str):
            raise VaultError("FORMAT_TEMPLATE_INVALID")
        if sha256_text(text) != company_format.template_digest:
            raise VaultError("FORMAT_TEMPLATE_DIGEST_MISMATCH")
        return text

    def capability_summary(self) -> "FormatCapabilitySummary":
        try:
            index = self._load_index()
            if set(index) != {"formats"} or not isinstance(index["formats"], dict):
                raise PolicyLoadError("FORMAT_INDEX_SCHEMA_INVALID")
            digests: list[str] = []
            active_count = 0
            for format_id, data in sorted(index["formats"].items()):
                if not isinstance(format_id, str) or not isinstance(data, dict):
                    raise PolicyLoadError("FORMAT_INDEX_SCHEMA_INVALID")
                validate_company_format_dict(data)
                if data.get("format_id") != format_id:
                    raise PolicyLoadError("FORMAT_ID_MISMATCH")
                if data["format_digest"] != compute_format_digest(data):
                    raise PolicyLoadError("FORMAT_DIGEST_MISMATCH")
                digests.append(data["format_digest"])
                if data.get("status") == "ACTIVE":
                    active_count += 1
            index_digest = stable_json_digest(
                {
                    "schema_version": 1,
                    "format_digests": digests,
                    "active_count": active_count,
                }
            ).removeprefix("sha256:")
            return FormatCapabilitySummary(
                active_count=active_count,
                registered_count=len(digests),
                format_digests=tuple(digests),
                active_format_digests=tuple(
                    sorted(
                        data["format_digest"]
                        for data in index["formats"].values()
                        if data.get("status") == "ACTIVE"
                    )
                ),
                index_digest=index_digest,
            )
        except PolicyLoadError:
            raise
        except Exception as exc:
            raise PolicyLoadError("FORMAT_CAPABILITY_LOAD_FAILED") from exc


@dataclass(frozen=True)
class FormatCapabilitySummary:
    active_count: int
    registered_count: int
    format_digests: tuple[str, ...]
    active_format_digests: tuple[str, ...]
    index_digest: str
