from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from .normalizer import (
    account_number_hint,
    holder_alias_hint,
    normalize_account_number,
    normalize_company_alias,
    normalize_holder_alias,
    unique_normalized,
)


SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
VAULT_REF_RE = re.compile(r"^local-vault://[A-Za-z0-9_.:/-]+$")
STATUS_VALUES = {"ACTIVE", "DEPRECATED"}
BANK_CODE_RE = re.compile(r"^[A-Z0-9._:-]{2,16}$")


class ContractValidationError(ValueError):
    pass


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json_digest(value: Any) -> str:
    return sha256_text(stable_json(value))


def require_digest(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.match(value):
        raise ContractValidationError(f"{field_name}_DIGEST_INVALID")
    return value


def _require_str_list(values: Any, field_name: str, *, required: bool) -> list[str]:
    if not isinstance(values, list):
        raise ContractValidationError(f"{field_name}_NOT_LIST")
    cleaned = [str(item).strip() for item in values if str(item or "").strip()]
    if required and not cleaned:
        raise ContractValidationError(f"{field_name}_REQUIRED")
    return cleaned


def _require_bank_accounts(values: Any, *, required: bool) -> list[dict[str, str]]:
    if not isinstance(values, list):
        raise ContractValidationError("OWN_BANK_ACCOUNTS_NOT_LIST")
    cleaned: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        if not isinstance(item, dict) or set(item) != {"bank_code", "account_number"}:
            raise ContractValidationError("OWN_BANK_ACCOUNT_INVALID")
        bank_code = str(item["bank_code"]).strip().upper()
        account_number = str(item["account_number"]).strip()
        normalized_account = normalize_account_number(account_number)
        if not BANK_CODE_RE.fullmatch(bank_code) or not normalized_account:
            raise ContractValidationError("OWN_BANK_ACCOUNT_INVALID")
        identity = (bank_code, normalized_account)
        if identity in seen:
            raise ContractValidationError("OWN_BANK_ACCOUNT_DUPLICATE")
        seen.add(identity)
        cleaned.append({"bank_code": bank_code, "account_number": account_number})
    if required and not cleaned:
        raise ContractValidationError("OWN_BANK_ACCOUNTS_REQUIRED")
    return cleaned


@dataclass(frozen=True)
class CompanyProfileRuntime:
    schema_version: Literal["company_profile.runtime.v1", "company_profile.runtime.v2"]
    profile_id: str
    status: Literal["ACTIVE", "DEPRECATED"]
    own_bank_holder_aliases: list[str]
    own_company_aliases: list[str]
    own_account_numbers: list[str]
    normalized_holder_keys: list[str]
    normalized_company_keys: list[str]
    normalized_account_numbers: list[str]
    profile_digest: str
    raw_text_logged: Literal[False]
    external_send_zero: Literal[True]
    plaintext_persisted: Literal[False]
    own_bank_accounts: list[dict[str, str]] = field(default_factory=list)

    def to_vault_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_runtime_profile_dict(data)
        return data


CompanyProfile = CompanyProfileRuntime


@dataclass(frozen=True)
class CompanyProfileIndexEntry:
    schema_version: Literal["company_profile.index.v1"]
    profile_id: str
    status: Literal["ACTIVE", "DEPRECATED"]
    profile_ref: str
    profile_digest: str
    field_digests: dict[str, list[str]]
    display_hints: dict[str, str]
    raw_text_logged: Literal[False]
    external_send_zero: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        validate_index_entry_dict(data)
        return data


def _field_digests(runtime: CompanyProfileRuntime) -> dict[str, list[str]]:
    values = {
        "own_bank_holder_aliases": [sha256_text(normalize_holder_alias(v)) for v in runtime.own_bank_holder_aliases],
        "own_company_aliases": [sha256_text(normalize_company_alias(v)) for v in runtime.own_company_aliases],
        "own_account_numbers": [sha256_text(normalize_account_number(v)) for v in runtime.own_account_numbers],
    }
    values["own_bank_accounts"] = [
        sha256_text(
            str(item["bank_code"]).upper()
            + "|"
            + normalize_account_number(item["account_number"])
        )
        for item in runtime.own_bank_accounts
    ]
    return values


def make_runtime_profile(
    *,
    own_bank_holder_aliases: list[str],
    own_company_aliases: list[str],
    own_account_numbers: list[str] | None = None,
    own_bank_accounts: list[dict[str, str]] | None = None,
    profile_id: str | None = None,
    status: str = "ACTIVE",
) -> CompanyProfileRuntime:
    holder_aliases = _require_str_list(own_bank_holder_aliases, "OWN_BANK_HOLDER_ALIASES", required=True)
    company_aliases = _require_str_list(own_company_aliases, "OWN_COMPANY_ALIASES", required=True)
    bank_accounts = _require_bank_accounts(own_bank_accounts or [], required=False)
    account_numbers = _require_str_list(own_account_numbers or [], "OWN_ACCOUNT_NUMBERS", required=False)
    account_numbers.extend(item["account_number"] for item in bank_accounts)
    account_numbers = list(dict.fromkeys(account_numbers))
    if status not in STATUS_VALUES:
        raise ContractValidationError("COMPANY_PROFILE_STATUS_INVALID")

    normalized_holder_keys = unique_normalized(holder_aliases, normalize_holder_alias)
    normalized_company_keys = unique_normalized(company_aliases, normalize_company_alias)
    normalized_accounts = unique_normalized(account_numbers, normalize_account_number)
    if not normalized_holder_keys:
        raise ContractValidationError("OWN_BANK_HOLDER_ALIASES_NORMALIZED_EMPTY")
    if not normalized_company_keys:
        raise ContractValidationError("OWN_COMPANY_ALIASES_NORMALIZED_EMPTY")

    data = {
        "schema_version": "company_profile.runtime.v2",
        "profile_id": profile_id or "profile-" + uuid.uuid4().hex,
        "status": status,
        "own_bank_holder_aliases": holder_aliases,
        "own_company_aliases": company_aliases,
        "own_account_numbers": account_numbers,
        "normalized_holder_keys": normalized_holder_keys,
        "normalized_company_keys": normalized_company_keys,
        "normalized_account_numbers": normalized_accounts,
        "raw_text_logged": False,
        "external_send_zero": True,
        "plaintext_persisted": False,
        "own_bank_accounts": bank_accounts,
    }
    data["profile_digest"] = stable_json_digest(data)
    runtime = CompanyProfileRuntime(**data)  # type: ignore[arg-type]
    validate_runtime_profile_dict(runtime.to_vault_dict())
    return runtime


def make_index_entry(*, runtime: CompanyProfileRuntime, profile_ref: str) -> CompanyProfileIndexEntry:
    holder_hint = next((holder_alias_hint(v) for v in runtime.own_bank_holder_aliases if holder_alias_hint(v)), None)
    account_hint = next((account_number_hint(v) for v in runtime.own_account_numbers if account_number_hint(v)), None)
    display_hints = {}
    if holder_hint:
        display_hints["holder_alias_hint"] = holder_hint
    if account_hint:
        display_hints["account_hint"] = account_hint
    entry = CompanyProfileIndexEntry(
        schema_version="company_profile.index.v1",
        profile_id=runtime.profile_id,
        status=runtime.status,
        profile_ref=profile_ref,
        profile_digest=runtime.profile_digest,
        field_digests=_field_digests(runtime),
        display_hints=display_hints,
        raw_text_logged=False,
        external_send_zero=True,
    )
    validate_index_entry_dict(entry.to_dict())
    return entry


def validate_runtime_profile_dict(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "profile_id", "status", "own_bank_holder_aliases",
        "own_company_aliases", "own_account_numbers", "normalized_holder_keys",
        "normalized_company_keys", "normalized_account_numbers", "profile_digest",
        "raw_text_logged", "external_send_zero", "plaintext_persisted",
        "own_bank_accounts",
    }
    if not isinstance(data, dict):
        raise ContractValidationError("COMPANY_PROFILE_RUNTIME_NOT_OBJECT")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractValidationError(f"COMPANY_PROFILE_RUNTIME_UNKNOWN_FIELD_{unknown[0]}")
    if data.get("schema_version") not in {
        "company_profile.runtime.v1",
        "company_profile.runtime.v2",
    }:
        raise ContractValidationError("COMPANY_PROFILE_RUNTIME_SCHEMA_INVALID")
    if data.get("status") not in STATUS_VALUES:
        raise ContractValidationError("COMPANY_PROFILE_RUNTIME_STATUS_INVALID")
    _require_str_list(data.get("own_bank_holder_aliases"), "OWN_BANK_HOLDER_ALIASES", required=True)
    _require_str_list(data.get("own_company_aliases"), "OWN_COMPANY_ALIASES", required=True)
    _require_str_list(data.get("own_account_numbers"), "OWN_ACCOUNT_NUMBERS", required=False)
    _require_str_list(data.get("normalized_holder_keys"), "NORMALIZED_HOLDER_KEYS", required=True)
    _require_str_list(data.get("normalized_company_keys"), "NORMALIZED_COMPANY_KEYS", required=True)
    _require_str_list(data.get("normalized_account_numbers"), "NORMALIZED_ACCOUNT_NUMBERS", required=False)
    if data.get("schema_version") == "company_profile.runtime.v2":
        _require_bank_accounts(data.get("own_bank_accounts"), required=False)
    elif "own_bank_accounts" in data:
        _require_bank_accounts(data.get("own_bank_accounts"), required=False)
    require_digest(data.get("profile_digest"), "profile")
    if data.get("raw_text_logged") is not False:
        raise ContractValidationError("COMPANY_PROFILE_RAW_TEXT_LOGGED_MUST_BE_FALSE")
    if data.get("external_send_zero") is not True:
        raise ContractValidationError("COMPANY_PROFILE_EXTERNAL_SEND_ZERO_REQUIRED")
    if data.get("plaintext_persisted") is not False:
        raise ContractValidationError("COMPANY_PROFILE_PLAINTEXT_PERSISTED_MUST_BE_FALSE")
    expected = stable_json_digest({k: v for k, v in data.items() if k != "profile_digest"})
    if data["profile_digest"] != expected:
        raise ContractValidationError("COMPANY_PROFILE_DIGEST_MISMATCH")
    return data


def validate_index_entry_dict(data: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema_version", "profile_id", "status", "profile_ref", "profile_digest",
        "field_digests", "display_hints", "raw_text_logged", "external_send_zero",
    }
    if not isinstance(data, dict):
        raise ContractValidationError("COMPANY_PROFILE_INDEX_NOT_OBJECT")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractValidationError(f"COMPANY_PROFILE_INDEX_UNKNOWN_FIELD_{unknown[0]}")
    if data.get("schema_version") != "company_profile.index.v1":
        raise ContractValidationError("COMPANY_PROFILE_INDEX_SCHEMA_INVALID")
    if data.get("status") not in STATUS_VALUES:
        raise ContractValidationError("COMPANY_PROFILE_INDEX_STATUS_INVALID")
    if not isinstance(data.get("profile_ref"), str) or not VAULT_REF_RE.match(data["profile_ref"]):
        raise ContractValidationError("COMPANY_PROFILE_REF_INVALID")
    require_digest(data.get("profile_digest"), "profile")
    field_digests = data.get("field_digests")
    if not isinstance(field_digests, dict):
        raise ContractValidationError("COMPANY_PROFILE_FIELD_DIGESTS_INVALID")
    for field_name in ("own_bank_holder_aliases", "own_company_aliases", "own_account_numbers"):
        values = field_digests.get(field_name)
        if not isinstance(values, list):
            raise ContractValidationError(f"COMPANY_PROFILE_FIELD_DIGESTS_{field_name}_INVALID")
        for value in values:
            require_digest(value, field_name)
    bank_account_digests = field_digests.get("own_bank_accounts", [])
    if not isinstance(bank_account_digests, list):
        raise ContractValidationError("COMPANY_PROFILE_FIELD_DIGESTS_OWN_BANK_ACCOUNTS_INVALID")
    for value in bank_account_digests:
        require_digest(value, "own_bank_accounts")
    display_hints = data.get("display_hints")
    if not isinstance(display_hints, dict):
        raise ContractValidationError("COMPANY_PROFILE_DISPLAY_HINTS_INVALID")
    if data.get("raw_text_logged") is not False:
        raise ContractValidationError("COMPANY_PROFILE_INDEX_RAW_TEXT_LOGGED_MUST_BE_FALSE")
    if data.get("external_send_zero") is not True:
        raise ContractValidationError("COMPANY_PROFILE_INDEX_EXTERNAL_SEND_ZERO_REQUIRED")
    return data
