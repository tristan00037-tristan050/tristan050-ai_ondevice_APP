from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Literal

from .contracts import (
    ROLE_VALUES,
    ContractValidationError,
    now_utc,
    require_digest,
    stable_json_digest,
)


ROLE_REGISTRY_ENTRY_SCHEMA = "company_policy.role_registry_entry.v1"
ROLE_REGISTRY_INDEX_ENTRY_SCHEMA = "company_policy.role_registry_index_entry.v1"
ROLE_REGISTRY_INDEX_FILE_SCHEMA = "company_policy.role_registry_index_file.v1"
ROLE_REGISTRY_STATUS_VALUES = {"ACTIVE", "REMOVED"}


class RoleRegistryContractError(ValueError):
    pass


@dataclass(frozen=True)
class RoleRegistryEntry:
    schema_version: Literal["company_policy.role_registry_entry.v1"]
    target_admin_id_digest: str
    role: Literal["admin", "manager", "employee"]
    status: Literal["ACTIVE", "REMOVED"]
    version: int
    registered_by_digest: str
    updated_by_digest: str
    updated_at: str
    previous_entry_digest: str | None
    raw_text_logged: Literal[False]
    external_send_zero: Literal[True]
    entry_digest: str

    def unsigned_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data.pop("entry_digest", None)
        return data

    def to_vault_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_role_registry_entry_dict(data)
        expected = compute_role_registry_entry_digest(data)
        if data["entry_digest"] != expected:
            raise RoleRegistryContractError("ROLE_REGISTRY_ENTRY_DIGEST_MISMATCH")
        return data


@dataclass(frozen=True)
class RoleRegistryIndexEntry:
    schema_version: Literal["company_policy.role_registry_index_entry.v1"]
    target_admin_id_digest: str
    role: Literal["admin", "manager", "employee"]
    status: Literal["ACTIVE", "REMOVED"]
    entry_ref: str
    entry_digest: str
    updated_at: str
    raw_text_logged: Literal[False]
    external_send_zero: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_role_registry_index_entry_dict(data)
        return data


def _require_digest_or_none(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return require_digest(value, field_name)


def _validate_common_flags(data: dict[str, Any], object_name: str) -> None:
    if data.get("raw_text_logged") is not False:
        raise RoleRegistryContractError(f"{object_name}_RAW_TEXT_LOGGED")
    if data.get("external_send_zero") is not True:
        raise RoleRegistryContractError(f"{object_name}_EXTERNAL_SEND_REQUIRED")


def validate_role_registry_entry_dict(data: dict[str, Any]) -> None:
    allowed = {
        "schema_version",
        "target_admin_id_digest",
        "role",
        "status",
        "version",
        "registered_by_digest",
        "updated_by_digest",
        "updated_at",
        "previous_entry_digest",
        "raw_text_logged",
        "external_send_zero",
        "entry_digest",
    }
    if set(data) != allowed:
        raise RoleRegistryContractError("ROLE_REGISTRY_ENTRY_FIELDS_INVALID")
    if data.get("schema_version") != ROLE_REGISTRY_ENTRY_SCHEMA:
        raise RoleRegistryContractError("ROLE_REGISTRY_ENTRY_SCHEMA_INVALID")
    require_digest(data.get("target_admin_id_digest"), "target_admin_id")
    require_digest(data.get("registered_by_digest"), "registered_by")
    require_digest(data.get("updated_by_digest"), "updated_by")
    _require_digest_or_none(data.get("previous_entry_digest"), "previous_entry")
    require_digest(data.get("entry_digest"), "entry")
    if data.get("role") not in ROLE_VALUES:
        raise RoleRegistryContractError("ROLE_REGISTRY_ROLE_INVALID")
    if data.get("status") not in ROLE_REGISTRY_STATUS_VALUES:
        raise RoleRegistryContractError("ROLE_REGISTRY_STATUS_INVALID")
    if not isinstance(data.get("version"), int) or data["version"] < 1:
        raise RoleRegistryContractError("ROLE_REGISTRY_VERSION_INVALID")
    if not isinstance(data.get("updated_at"), str) or not data["updated_at"]:
        raise RoleRegistryContractError("ROLE_REGISTRY_UPDATED_AT_INVALID")
    _validate_common_flags(data, "ROLE_REGISTRY_ENTRY")


def validate_role_registry_index_entry_dict(data: dict[str, Any]) -> None:
    allowed = {
        "schema_version",
        "target_admin_id_digest",
        "role",
        "status",
        "entry_ref",
        "entry_digest",
        "updated_at",
        "raw_text_logged",
        "external_send_zero",
    }
    if set(data) != allowed:
        raise RoleRegistryContractError("ROLE_REGISTRY_INDEX_ENTRY_FIELDS_INVALID")
    if data.get("schema_version") != ROLE_REGISTRY_INDEX_ENTRY_SCHEMA:
        raise RoleRegistryContractError("ROLE_REGISTRY_INDEX_ENTRY_SCHEMA_INVALID")
    require_digest(data.get("target_admin_id_digest"), "target_admin_id")
    require_digest(data.get("entry_digest"), "entry")
    if data.get("role") not in ROLE_VALUES:
        raise RoleRegistryContractError("ROLE_REGISTRY_INDEX_ROLE_INVALID")
    if data.get("status") not in ROLE_REGISTRY_STATUS_VALUES:
        raise RoleRegistryContractError("ROLE_REGISTRY_INDEX_STATUS_INVALID")
    if not isinstance(data.get("entry_ref"), str) or not data["entry_ref"].startswith("local-vault://role_registry/"):
        raise RoleRegistryContractError("ROLE_REGISTRY_INDEX_REF_INVALID")
    if not isinstance(data.get("updated_at"), str) or not data["updated_at"]:
        raise RoleRegistryContractError("ROLE_REGISTRY_INDEX_UPDATED_AT_INVALID")
    _validate_common_flags(data, "ROLE_REGISTRY_INDEX_ENTRY")


def compute_role_registry_entry_digest(data: dict[str, Any]) -> str:
    unsigned = dict(data)
    unsigned.pop("entry_digest", None)
    return stable_json_digest(unsigned)


def make_role_registry_entry(
    *,
    target_admin_id_digest: str,
    role: str,
    status: str,
    registered_by_digest: str,
    updated_by_digest: str,
    version: int,
    previous_entry_digest: str | None = None,
    updated_at: str | None = None,
) -> RoleRegistryEntry:
    data: dict[str, Any] = {
        "schema_version": ROLE_REGISTRY_ENTRY_SCHEMA,
        "target_admin_id_digest": require_digest(target_admin_id_digest, "target_admin_id"),
        "role": role,
        "status": status,
        "version": version,
        "registered_by_digest": require_digest(registered_by_digest, "registered_by"),
        "updated_by_digest": require_digest(updated_by_digest, "updated_by"),
        "updated_at": updated_at or now_utc(),
        "previous_entry_digest": _require_digest_or_none(previous_entry_digest, "previous_entry"),
        "raw_text_logged": False,
        "external_send_zero": True,
    }
    data["entry_digest"] = compute_role_registry_entry_digest(data)
    validate_role_registry_entry_dict(data)
    return RoleRegistryEntry(**data)


def make_role_registry_index_entry(*, entry: RoleRegistryEntry, entry_ref: str) -> RoleRegistryIndexEntry:
    data = {
        "schema_version": ROLE_REGISTRY_INDEX_ENTRY_SCHEMA,
        "target_admin_id_digest": entry.target_admin_id_digest,
        "role": entry.role,
        "status": entry.status,
        "entry_ref": entry_ref,
        "entry_digest": entry.entry_digest,
        "updated_at": entry.updated_at,
        "raw_text_logged": False,
        "external_send_zero": True,
    }
    validate_role_registry_index_entry_dict(data)
    return RoleRegistryIndexEntry(**data)
