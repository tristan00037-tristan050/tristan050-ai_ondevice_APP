from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from butler_pc_core.company_policy.admin_auth import AdminAuthError, admin_error_payload, verify_admin_context
from butler_pc_core.company_policy.contracts import (
    AccessRule,
    AdminContext,
    ContractValidationError,
    make_company_policy,
    sha256_text,
)
from butler_pc_core.company_policy.policy_gate import PolicyGate, build_policy_task_envelope
from butler_pc_core.company_policy.storage import CompanyFormatStore, PolicyLoadError, PolicyStore

router = APIRouter()

_POLICY_STORE: PolicyStore | None = None
_FORMAT_STORE: CompanyFormatStore | None = None


def get_policy_store() -> PolicyStore:
    global _POLICY_STORE
    if _POLICY_STORE is None:
        _POLICY_STORE = PolicyStore()
    return _POLICY_STORE


def get_format_store() -> CompanyFormatStore:
    global _FORMAT_STORE
    if _FORMAT_STORE is None:
        _FORMAT_STORE = CompanyFormatStore()
    return _FORMAT_STORE


class AccessRulePayload(BaseModel):
    dept_digest: str
    role: str
    doc_grade: str
    decision: str
    reason_code: str


class CompanyPolicyRegisterRequest(BaseModel):
    version: int = Field(default=1, ge=1)
    status: str = "ACTIVE"
    access_rules: list[AccessRulePayload]
    masking_engine_verified: bool = False


class CompanyFormatRegisterRequest(BaseModel):
    template_runtime_text: str = Field(..., min_length=1, max_length=200000)
    format_kind: str
    title_runtime_text: str = Field(..., min_length=1, max_length=1000)
    language: str = "ko"
    dept_digest: str


class PolicyGateEvaluateRequest(BaseModel):
    request_id: str
    tenant_digest: str
    dept_digest: str
    user_role: str
    target_box_id: str
    operation: str
    doc_grade: str
    external_send_requested: bool = False
    # 박스 3 머지본 환경(Python 3.9) pydantic BaseModel type hints 는 eager evaluation
    # 되므로 `Optional[str]` 신문법 대신 typing.Optional 사용 (`from __future__ import
    # annotations` 는 함수 시그니처만 lazy 적용).
    format_id: Optional[str] = None
    learning_allowed: bool = False
    retention_days: int = 30
    masking_requested: bool = False


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


@router.post("/v1/admin/company-policy")
async def register_company_policy(
    payload: CompanyPolicyRegisterRequest,
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        admin = verify_admin_context(
            _admin_context(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method),
            operation="register_company_policy",
        )
        rules = [AccessRule(**item.dict()) for item in payload.access_rules]
        policy = make_company_policy(
            registered_by_digest=admin.admin_id_digest,
            access_rules=rules,
            version=payload.version,
            status=payload.status,
            masking_engine_verified=payload.masking_engine_verified,
        )
        audit = get_policy_store().save_policy(policy, admin)
        return {
            "schema_version": "admin.company_policy_register.response.v1",
            "policy_digest": policy.policy_digest,
            "audit_ref": audit["audit_id"],
            "admin_rbac_verified": True,
            "raw_saved_zero": True,
            "raw_text_logged": False,
        }
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except (ContractValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail={"fail_class": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/v1/admin/company-format")
async def register_company_format(
    payload: CompanyFormatRegisterRequest,
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        admin = verify_admin_context(
            _admin_context(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method),
            operation="register_company_format",
        )
        fmt, audit = get_format_store().register_format(
            template_runtime_text=payload.template_runtime_text,
            format_kind=payload.format_kind,
            title_runtime_text=payload.title_runtime_text,
            language=payload.language,
            dept_digest=payload.dept_digest,
            admin=admin,
        )
        return {
            "schema_version": "admin.company_format_register.response.v1",
            "format_id": fmt.format_id,
            "format_digest": fmt.format_digest,
            "template_digest": fmt.template_digest,
            "template_ref": fmt.template_ref,
            "audit_ref": audit["audit_id"],
            "encrypted_store": True,
            "raw_saved_zero": True,
            "raw_text_logged": False,
        }
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except (ContractValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail={"fail_class": exc.__class__.__name__, "message": str(exc)}) from exc


@router.post("/v1/policy/evaluate")
async def evaluate_policy(payload: PolicyGateEvaluateRequest) -> dict[str, Any]:
    try:
        active = get_policy_store().load_active_policy()
    except PolicyLoadError:
        active = None
        gate = PolicyGate.evaluate(
            build_policy_task_envelope(
                request_id=payload.request_id,
                tenant_digest=payload.tenant_digest,
                dept_digest=payload.dept_digest,
                user_role=payload.user_role,
                target_box_id=payload.target_box_id,
                operation=payload.operation,
                doc_grade=payload.doc_grade,
                external_send_requested=payload.external_send_requested,
                format_id=payload.format_id,
                learning_allowed=payload.learning_allowed,
                retention_days=payload.retention_days,
                masking_requested=payload.masking_requested,
            ),
            None,
        )
        return gate.to_dict()
    env = build_policy_task_envelope(**payload.dict())
    return PolicyGate.evaluate(env, active).to_dict()


@router.get("/v1/admin/company-format/{format_id}/adapter")
async def format_adapter_preview(format_id: str, draft_digest: Optional[str] = None) -> dict[str, Any]:
    # 박스 3 real adapter 위치 정합 (표준 156): runtime helper3 application 은
    # `butler_pc_core/cards/box3/adapters/company_format_adapter.py::apply_company_format_runtime`
    # 단일 경로가 정본이며 raw runtime text 가 있는 박스 3 파이프라인 내부에서만 수행된다.
    # 본 sidecar endpoint 는 raw text 가 없으므로 format 등록·활성 상태와 digest 메타만 노출
    # (raw 0 / digest-only). draft_digest 는 caller-side 정합 키로만 echo 한다.
    company_format = get_format_store().get_format(format_id)
    if company_format is None:
        return {
            "schema_version": "helper3.company_format_adapter.v1",
            "format_id": format_id,
            "registered": False,
            "active": False,
            "format_digest": None,
            "template_digest": None,
            "needs_review": True,
            "reason_code": "FORMAT_NOT_REGISTERED",
            "draft_digest_echo": draft_digest,
        }
    is_active = company_format.status == "ACTIVE"
    return {
        "schema_version": "helper3.company_format_adapter.v1",
        "format_id": company_format.format_id,
        "registered": True,
        "active": is_active,
        "format_digest": company_format.format_digest,
        "template_digest": company_format.template_digest,
        "needs_review": not is_active,
        "reason_code": None if is_active else "FORMAT_NOT_ACTIVE",
        "draft_digest_echo": draft_digest,
    }
