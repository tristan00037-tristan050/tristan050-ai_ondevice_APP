from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from butler_pc_core.auth.capability_token import (
    CapabilityTokenError,
    CapabilityTokenManager,
    auth_error_payload,
)
from butler_pc_core.company_policy.admin_auth import (
    AdminAuthError,
    _verify_admin_context_base,
    admin_error_payload,
    verify_admin_context,
)
from butler_pc_core.company_policy.contracts import AdminContext, ContractValidationError
from butler_pc_core.company_policy.role_registry import (
    RoleRegistryLoadError,
    RoleRegistryMutationError,
    RoleRegistryStore,
    get_default_role_registry_store,
)
from butler_pc_core.company_policy.role_registry_contracts import RoleRegistryContractError


router = APIRouter()
_TOKEN_MANAGER = CapabilityTokenManager()
_STORE: RoleRegistryStore | None = None


class RoleRegistryBootstrapRequest(BaseModel):
    target_admin_id_digest: Optional[str] = None
    role: str = "admin"


class RoleRegistryMemberRequest(BaseModel):
    target_admin_id_digest: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)


def get_role_registry_store() -> RoleRegistryStore:
    global _STORE
    if _STORE is None:
        return get_default_role_registry_store()
    return _STORE


def _verify_token(authorization: Optional[str]) -> None:
    try:
        _TOKEN_MANAGER.verify_authorization_header(authorization)
    except CapabilityTokenError as exc:
        status = 401 if exc.fail_class.value == "CAPABILITY_TOKEN_MISSING" else 403
        raise HTTPException(status_code=status, detail=auth_error_payload(exc)) from exc


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


def _http_for_registry_error(exc: Exception) -> int:
    fail_class = str(exc)
    if fail_class.endswith("ALREADY_INITIALIZED") or fail_class.endswith("LAST_ADMIN"):
        return 409
    if fail_class.endswith("ROLE_INVALID") or fail_class.endswith("TARGET_NOT_FOUND"):
        return 400
    return 403


def _entry_response(schema_version: str, entry: Any, audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "target_admin_id_digest": entry.target_admin_id_digest,
        "role": entry.role,
        "status": entry.status,
        "entry_digest": entry.entry_digest,
        "audit_ref": audit["audit_id"],
        "raw_text_logged": False,
        "external_send_zero": True,
    }


@router.post("/v1/admin/role-registry/bootstrap")
async def bootstrap_role_registry(
    payload: RoleRegistryBootstrapRequest,
    authorization: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _verify_token(authorization)
    try:
        actor = _verify_admin_context_base(
            _admin_context(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method),
            operation="bootstrap_role_registry",
        )
        target = payload.target_admin_id_digest or actor.admin_id_digest
        if target != actor.admin_id_digest or payload.role != "admin":
            raise AdminAuthError("ADMIN_ROLE_REGISTRY_TARGET_MISMATCH", "bootstrap target must be self admin")
        entry, audit = get_role_registry_store().bootstrap_self_admin(actor)
        return _entry_response("admin.role_registry.bootstrap.response.v1", entry, audit)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except (ContractValidationError, RoleRegistryContractError) as exc:
        raise HTTPException(status_code=400, detail={"fail_class": "ADMIN_ROLE_REGISTRY_CONTRACT_INVALID"}) from exc
    except RoleRegistryMutationError as exc:
        raise HTTPException(status_code=_http_for_registry_error(exc), detail={"fail_class": str(exc)}) from exc
    except RoleRegistryLoadError as exc:
        raise HTTPException(status_code=503, detail={"fail_class": "ADMIN_ROLE_REGISTRY_LOAD_FAILED"}) from exc


@router.post("/v1/admin/role-registry/members")
async def upsert_role_registry_member(
    payload: RoleRegistryMemberRequest,
    authorization: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _verify_token(authorization)
    try:
        actor = verify_admin_context(
            _admin_context(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method),
            operation="upsert_role_registry_member",
        )
        entry, audit = get_role_registry_store().upsert_member(
            actor=actor,
            target_admin_id_digest=payload.target_admin_id_digest,
            role=payload.role,
        )
        return _entry_response("admin.role_registry.member.response.v1", entry, audit)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except (ContractValidationError, RoleRegistryContractError) as exc:
        raise HTTPException(status_code=400, detail={"fail_class": "ADMIN_ROLE_REGISTRY_CONTRACT_INVALID"}) from exc
    except RoleRegistryMutationError as exc:
        raise HTTPException(status_code=_http_for_registry_error(exc), detail={"fail_class": str(exc)}) from exc
    except RoleRegistryLoadError as exc:
        raise HTTPException(status_code=503, detail={"fail_class": "ADMIN_ROLE_REGISTRY_LOAD_FAILED"}) from exc


@router.delete("/v1/admin/role-registry/members/{target_admin_id_digest}")
async def remove_role_registry_member(
    target_admin_id_digest: str,
    authorization: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _verify_token(authorization)
    try:
        actor = verify_admin_context(
            _admin_context(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method),
            operation="remove_role_registry_member",
        )
        entry, audit = get_role_registry_store().remove_member(
            actor=actor,
            target_admin_id_digest=target_admin_id_digest,
        )
        return _entry_response("admin.role_registry.remove.response.v1", entry, audit)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except (ContractValidationError, RoleRegistryContractError) as exc:
        raise HTTPException(status_code=400, detail={"fail_class": "ADMIN_ROLE_REGISTRY_CONTRACT_INVALID"}) from exc
    except RoleRegistryMutationError as exc:
        raise HTTPException(status_code=_http_for_registry_error(exc), detail={"fail_class": str(exc)}) from exc
    except RoleRegistryLoadError as exc:
        raise HTTPException(status_code=503, detail={"fail_class": "ADMIN_ROLE_REGISTRY_LOAD_FAILED"}) from exc


@router.get("/v1/admin/role-registry/status")
async def role_registry_status(
    authorization: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _verify_token(authorization)
    try:
        status = get_role_registry_store().status_summary()
        context = _admin_context(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method)
        if status["initialized"]:
            verify_admin_context(context, operation="role_registry_status")
        else:
            _verify_admin_context_base(context, operation="role_registry_status")
        return {
            "schema_version": "admin.role_registry.status.response.v1",
            **status,
        }
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except RoleRegistryLoadError as exc:
        raise HTTPException(status_code=503, detail={"fail_class": "ADMIN_ROLE_REGISTRY_LOAD_FAILED"}) from exc
