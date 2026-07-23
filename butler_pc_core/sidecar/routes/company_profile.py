from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from typing import Any, Optional

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from butler_pc_core.accounting.assignment.domain import AssignmentError
from butler_pc_core.auth.capability_token import (
    CapabilityTokenError,
    CapabilityTokenManager,
    auth_error_payload,
)
from butler_pc_core.company_policy.admin_auth import AdminAuthError, admin_error_payload, verify_admin_context
from butler_pc_core.company_policy.contracts import AdminContext
from butler_pc_core.company_profile.contracts import (
    ContractValidationError,
    make_runtime_profile,
    sha256_text,
)
from butler_pc_core.company_profile.normalizer import holder_alias_hint, normalize_holder_alias
from butler_pc_core.company_profile.storage import CompanyProfileStore, ProfileLoadError


router = APIRouter()
_STORE: CompanyProfileStore | None = None
_TOKEN_MANAGER = CapabilityTokenManager()


class OwnBankAccountRequest(BaseModel):
    bank_code: str = Field(..., min_length=2, max_length=16)
    account_number: str = Field(..., min_length=1, max_length=64)


class CompanyProfileRegisterRequest(BaseModel):
    own_bank_holder_aliases: list[str] = Field(..., min_length=1)
    own_company_aliases: list[str] = Field(..., min_length=1)
    own_account_numbers: list[str] = Field(default_factory=list)
    own_bank_accounts: list[OwnBankAccountRequest] = Field(default_factory=list)


def get_company_profile_store() -> CompanyProfileStore:
    global _STORE
    if _STORE is None:
        _STORE = CompanyProfileStore()
    return _STORE


def _admin_context(
    x_admin_role: Optional[str],
    x_admin_id_digest: Optional[str],
    x_admin_session_digest: Optional[str],
    x_admin_auth_method: Optional[str],
) -> AdminContext:
    if not x_admin_id_digest or not x_admin_session_digest:
        raise AdminAuthError("ADMIN_AUTH_REQUIRED", "admin digest headers required")
    return AdminContext(
        admin_id_digest=x_admin_id_digest,
        role=x_admin_role or "employee",  # type: ignore[arg-type]
        admin_session_digest=x_admin_session_digest,
        auth_method=x_admin_auth_method or "tauri_secure_invoke",  # type: ignore[arg-type]
    )


@router.get("/v1/company-profile/status")
async def company_profile_status(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    try:
        _TOKEN_MANAGER.verify_authorization_header(authorization)
    except CapabilityTokenError as exc:
        status = 401 if exc.fail_class.value == "CAPABILITY_TOKEN_MISSING" else 403
        raise HTTPException(status_code=status, detail=auth_error_payload(exc)) from exc

    try:
        entry = get_company_profile_store().load_active_index()
        if entry is not None:
            runtime = get_company_profile_store().load_active_profile()
            if runtime is None:
                raise ProfileLoadError("COMPANY_PROFILE_LOAD_FAILED")
    except ProfileLoadError as exc:
        raise HTTPException(status_code=503, detail={"fail_class": "COMPANY_PROFILE_LOAD_FAILED"}) from exc
    if entry is None:
        return {
            "schema_version": "company_profile.status.v1",
            "active": False,
            "profile_id": None,
            "profile_digest": None,
            "display_hints": {},
            "raw_text_logged": False,
            "external_send_zero": True,
        }
    return {
        "schema_version": "company_profile.status.v1",
        "active": entry.status == "ACTIVE",
        "profile_id": entry.profile_id,
        "profile_digest": entry.profile_digest,
        "display_hints": entry.display_hints,
        "raw_text_logged": False,
        "external_send_zero": True,
    }


@router.post("/v1/company-profile/register")
async def register_company_profile(
    payload: CompanyProfileRegisterRequest,
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        admin = _admin_context(
            x_admin_role,
            x_admin_id_digest,
            x_admin_session_digest,
            x_admin_auth_method,
        )
        verify_admin_context(
            admin,
            operation="register_company_profile",
        )
        runtime = make_runtime_profile(
            own_bank_holder_aliases=payload.own_bank_holder_aliases,
            own_company_aliases=payload.own_company_aliases,
            own_account_numbers=payload.own_account_numbers,
            own_bank_accounts=[item.model_dump() for item in payload.own_bank_accounts],
        )
        registry_digest = None
        if runtime.own_bank_accounts:
            from butler_pc_core.accounting.assignment.runtime import (
                get_accounting_review_runtime,
            )
            from butler_pc_core.accounting.classify.reconciliation_v2 import tenant_uuid

            registry = get_accounting_review_runtime().store.replace_a4_own_account_registry(
                tenant_id=tenant_uuid(runtime.profile_id),
                accounts=runtime.own_bank_accounts,
                approval_id=admin.admin_id_digest,
                observed_at=datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            )
            registry_digest = registry["registry_digest"]
        entry = get_company_profile_store().save_profile(runtime)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except ContractValidationError as exc:
        raise HTTPException(status_code=422, detail={"fail_class": str(exc)}) from exc
    except AssignmentError as exc:
        raise HTTPException(status_code=exc.status, detail={"fail_class": exc.code}) from exc
    return {
        "schema_version": "company_profile.register.response.v1",
        "profile_id": entry.profile_id,
        "profile_digest": entry.profile_digest,
        "display_hints": entry.display_hints,
        "raw_text_logged": False,
        "plaintext_persisted": False,
        "external_send_zero": True,
        "a4_registry_ready": bool(runtime.own_bank_accounts),
        "a4_registry_digest": registry_digest,
    }


def _decode_upload_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _extract_holder_candidates(text: str) -> list[str]:
    reader = csv.DictReader(StringIO(text))
    candidate_columns = ("상대계좌예금주명", "보낸분/받는분", "받는분", "보내는분", "거래처", "상대처")
    seen: set[str] = set()
    values: list[str] = []
    for row in reader:
        for column in candidate_columns:
            value = str(row.get(column) or "").strip()
            key = normalize_holder_alias(value)
            if not key or key in seen:
                continue
            seen.add(key)
            values.append(value)
    return values[:10]


@router.post("/v1/company-profile/suggest-from-accounting-file")
async def suggest_from_accounting_file(file: Optional[UploadFile] = File(default=None)) -> dict[str, Any]:
    if file is None:
        raise HTTPException(status_code=422, detail={"fail_class": "COMPANY_PROFILE_FILE_REQUIRED"})
    raw = await file.read()
    text = _decode_upload_text(raw)
    candidates = _extract_holder_candidates(text)
    return {
        "schema_version": "company_profile.suggest.response.v1",
        "suggestions": [
            {
                "value_runtime_text": value,
                "normalized_key_digest": sha256_text(normalize_holder_alias(value)),
                "display_hint": holder_alias_hint(value),
            }
            for value in candidates
        ],
        "candidate_count": len(candidates),
        "persisted": False,
        "plaintext_persisted": False,
        "raw_text_logged": False,
        "external_send_zero": True,
    }
