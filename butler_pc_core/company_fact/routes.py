from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from butler_pc_core.auth.capability_token import (
    CapabilityTokenError,
    CapabilityTokenManager,
    auth_error_payload,
)
from butler_pc_core.company_policy.admin_auth import AdminAuthError, admin_error_payload, verify_admin_context
from butler_pc_core.company_policy.contracts import AdminContext

from .contracts import CompanyFactContractError
from .resolver import CompanyKnowledgeResolver
from .storage import CompanyFactLoadError, CompanyFactStore


router = APIRouter()
_STORE: CompanyFactStore | None = None
_TOKEN_MANAGER = CapabilityTokenManager()


class CompanyFactCandidateRequest(BaseModel):
    category: str
    question_patterns: list[str] = Field(..., min_length=2)
    keywords_required: list[str] = Field(default_factory=list)
    keywords_any: list[str] = Field(default_factory=list)
    answer_runtime_text: str = Field(..., min_length=10)
    source: str = Field(..., min_length=3)
    source_url: Optional[str] = None
    source_doc: Optional[str] = None
    verified_at: Optional[str] = None
    expires_at: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, lt=1.0)


class CompanyFactResolveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)


class CompanyFactDeprecateRequest(BaseModel):
    reason_code: str = Field(default="MANUAL_DEPRECATED", pattern=r"^(WRONG|SUPERSEDED|MANUAL_DEPRECATED)$")


class CompanyFactSupersedeRequest(CompanyFactCandidateRequest):
    confidence: float = Field(default=1.0, ge=1.0, le=1.0)


def get_company_fact_store() -> CompanyFactStore:
    global _STORE
    if _STORE is None:
        _STORE = CompanyFactStore()
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


def _verify_admin(
    x_admin_role: Optional[str],
    x_admin_id_digest: Optional[str],
    x_admin_session_digest: Optional[str],
    x_admin_auth_method: Optional[str],
    *,
    operation: str,
) -> AdminContext:
    return verify_admin_context(
        _admin_context(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method),
        operation=operation,
    )


def _candidate_detail(record) -> dict[str, Any]:
    return {
        "schema_version": "company_fact.candidate_detail.v1",
        "fact_id": record.fact_id,
        "status": record.status,
        "category": record.category,
        "question_patterns": record.question_patterns,
        "keywords_required": record.keywords_required,
        "keywords_any": record.keywords_any,
        "answer_runtime_text": record.answer_runtime_text,
        "source": record.source,
        "source_url": record.source_url,
        "source_doc": record.source_doc,
        "verified_at": record.verified_at,
        "expires_at": record.expires_at,
        "confidence": record.confidence,
        "fact_digest": record.fact_digest,
        "raw_text_logged": False,
        "external_send_zero": True,
    }


def _candidate_detail_with_known_bad(store: CompanyFactStore, record) -> dict[str, Any]:
    data = _candidate_detail(record)
    data["known_bad"] = store.known_bad_flags_for_candidate(record)
    return data


@router.get("/v1/company-facts/status")
async def company_facts_status(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    _verify_token(authorization)
    store = get_company_fact_store()
    try:
        active_count = len(store.load_active_facts())
        candidate_count = len(store.list_index_entries(status="CANDIDATE"))
    except CompanyFactLoadError as exc:
        raise HTTPException(status_code=503, detail={"fail_class": "COMPANY_FACT_LOAD_FAILED"}) from exc
    return {
        "schema_version": "company_facts.status.v1",
        "active_count": active_count,
        "candidate_count": candidate_count,
        "raw_text_logged": False,
        "external_send_zero": True,
    }


@router.post("/v1/company-facts/resolve")
async def resolve_company_facts(
    payload: CompanyFactResolveRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _verify_token(authorization)
    resolver = CompanyKnowledgeResolver(company_store=get_company_fact_store())
    result = resolver.resolve(payload.query)
    if result.fail_class and result.source == "none":
        raise HTTPException(status_code=503, detail=result.to_dict())
    return result.to_dict()


@router.post("/v1/company-facts/candidates")
async def submit_company_fact_candidate(
    payload: CompanyFactCandidateRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    _verify_token(authorization)
    try:
        entry, audit = get_company_fact_store().save_candidate(**payload.model_dump())
    except CompanyFactContractError as exc:
        raise HTTPException(status_code=422, detail={"fail_class": str(exc)}) from exc
    return {
        "schema_version": "company_fact.candidate.response.v1",
        "fact_id": entry.fact_id,
        "status": entry.status,
        "fact_digest": entry.fact_digest,
        "audit_ref": audit["audit_id"],
        "raw_text_logged": False,
        "external_send_zero": True,
    }


@router.get("/v1/company-facts/candidates")
async def list_company_fact_candidates(
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        _verify_admin(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method, operation="list_company_fact_candidates")
        store = get_company_fact_store()
        entries = store.list_index_entries(status="CANDIDATE")
        rows = []
        for entry in entries:
            row = entry.to_dict()
            row["known_bad"] = store.known_bad_flags_for_candidate(store.load_fact(entry.fact_id))
            rows.append(row)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except CompanyFactLoadError as exc:
        raise HTTPException(status_code=503, detail={"fail_class": "COMPANY_FACT_LOAD_FAILED"}) from exc
    return {
        "schema_version": "company_fact.candidates.response.v1",
        "candidates": rows,
        "candidate_count": len(entries),
        "raw_text_logged": False,
        "external_send_zero": True,
    }


@router.get("/v1/company-facts/candidates/{fact_id}")
async def get_company_fact_candidate(
    fact_id: str,
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        _verify_admin(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method, operation="get_company_fact_candidate")
        store = get_company_fact_store()
        record = store.load_fact(fact_id)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except CompanyFactLoadError as exc:
        raise HTTPException(status_code=404, detail={"fail_class": str(exc)}) from exc
    if record.status != "CANDIDATE":
        raise HTTPException(status_code=404, detail={"fail_class": "COMPANY_FACT_CANDIDATE_NOT_FOUND"})
    return _candidate_detail_with_known_bad(store, record)


@router.post("/v1/company-facts/candidates/{fact_id}/approve")
async def approve_company_fact_candidate(
    fact_id: str,
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        admin = _verify_admin(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method, operation="approve_company_fact")
        entry, audit = get_company_fact_store().approve_candidate(fact_id, admin)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except (CompanyFactContractError, CompanyFactLoadError) as exc:
        status = 409 if str(exc) == "KNOWN_BAD_APPROVAL_BLOCKED" else 422
        raise HTTPException(status_code=status, detail={"fail_class": str(exc), "raw_text_logged": False, "external_send_zero": True}) from exc
    return {
        "schema_version": "company_fact.approve.response.v1",
        "fact_id": entry.fact_id,
        "status": entry.status,
        "fact_digest": entry.fact_digest,
        "audit_ref": audit["audit_id"],
        "raw_text_logged": False,
        "external_send_zero": True,
    }


@router.post("/v1/company-facts/{fact_id}/deprecate")
async def deprecate_company_fact(
    fact_id: str,
    payload: Optional[CompanyFactDeprecateRequest] = None,
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        admin = _verify_admin(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method, operation="deprecate_company_fact")
        entry, audit = get_company_fact_store().deprecate_fact(
            fact_id, admin, reason_code=(payload.reason_code if payload else "MANUAL_DEPRECATED")
        )
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except (CompanyFactContractError, CompanyFactLoadError) as exc:
        raise HTTPException(status_code=422, detail={"fail_class": str(exc), "raw_text_logged": False, "external_send_zero": True}) from exc
    return {
        "schema_version": "company_fact.deprecate.response.v1",
        "fact_id": entry.fact_id,
        "status": entry.status,
        "fact_digest": entry.fact_digest,
        "audit_ref": audit["audit_id"],
        "raw_text_logged": False,
        "external_send_zero": True,
    }


@router.post("/v1/company-facts/{fact_id}/supersede")
async def supersede_company_fact(
    fact_id: str,
    payload: CompanyFactSupersedeRequest,
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        admin = _verify_admin(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method, operation="supersede_company_fact")
        return get_company_fact_store().supersede_fact(fact_id, payload.model_dump(), admin)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except (CompanyFactContractError, CompanyFactLoadError) as exc:
        raise HTTPException(status_code=422, detail={"fail_class": str(exc), "raw_text_logged": False, "external_send_zero": True}) from exc


@router.post("/v1/company-facts/candidates/{fact_id}/known-bad/override")
async def override_known_bad_company_fact_candidate(
    fact_id: str,
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        admin = _verify_admin(x_admin_role, x_admin_id_digest, x_admin_session_digest, x_admin_auth_method, operation="override_known_bad_company_fact")
        result = get_company_fact_store().override_known_bad_candidate(fact_id, admin)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except (CompanyFactContractError, CompanyFactLoadError) as exc:
        raise HTTPException(status_code=422, detail={"fail_class": str(exc), "raw_text_logged": False, "external_send_zero": True}) from exc
    return {"schema_version": "company_fact.known_bad_override.response.v1", **result}
