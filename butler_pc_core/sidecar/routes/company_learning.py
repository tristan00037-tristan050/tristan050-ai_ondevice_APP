from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from butler_pc_core.auth.capability_token import (
    CapabilityTokenError,
    CapabilityTokenManager,
    auth_error_payload,
)
from butler_pc_core.company_learning.folder_ingest import CompanyLearningIngestError, ingest_folder
from butler_pc_core.company_learning.handoff import create_company_learning_candidate
from butler_pc_core.company_learning.job_store import CompanyLearningJobStore
from butler_pc_core.company_learning.understanding import build_understanding
from butler_pc_core.company_policy.admin_auth import AdminAuthError, admin_error_payload, verify_admin_context
from butler_pc_core.company_policy.contracts import AdminContext
from butler_pc_core.connect_loop.learning_event_store import LearningEventStore
from butler_pc_core.inference.llm_runtime import LlmRuntime

router = APIRouter()
_TOKEN_MANAGER = CapabilityTokenManager()
_JOB_STORE = CompanyLearningJobStore()
_LEARNING_EVENT_STORE = LearningEventStore()
_LLM_RUNTIME: LlmRuntime | None = None
LOCALHOST_HOSTS = {"127.0.0.1", "localhost", "::1", "testclient"}


class CompanyLearningConnectRequest(BaseModel):
    folder_path: str = Field(..., min_length=1)


class CompanyLearningHandoffRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    admin_confirmed_needs_review: bool = False


def _error_detail(fail_class: str, message: str | None = None) -> dict[str, Any]:
    return {
        "fail_class": fail_class,
        "message": message or fail_class,
        "raw_text_logged": False,
        "external_send_zero": True,
    }


def _verify_token(authorization: Optional[str]) -> None:
    try:
        _TOKEN_MANAGER.verify_authorization_header(authorization)
    except CapabilityTokenError as exc:
        status = 401 if exc.fail_class.value == "CAPABILITY_TOKEN_MISSING" else 403
        raise HTTPException(status_code=status, detail=auth_error_payload(exc)) from exc


def _verify_localhost(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in LOCALHOST_HOSTS:
        raise HTTPException(status_code=403, detail=_error_detail("LOCALHOST_ONLY", "localhost only"))


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


def _llm_status() -> str:
    if _LLM_RUNTIME is None:
        return "not_used"
    return _LLM_RUNTIME.status if _LLM_RUNTIME.status in {"ready", "no_model", "error"} else "error"


def _authorized_admin(
    authorization: Optional[str],
    x_admin_role: Optional[str],
    x_admin_id_digest: Optional[str],
    x_admin_session_digest: Optional[str],
    x_admin_auth_method: Optional[str],
    *,
    operation: str,
) -> None:
    _verify_token(authorization)
    _verify_admin(
        x_admin_role,
        x_admin_id_digest,
        x_admin_session_digest,
        x_admin_auth_method,
        operation=operation,
    )


@router.post("/v1/company-learning/folder/connect")
async def connect_company_learning_folder(
    payload: CompanyLearningConnectRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        _verify_localhost(request)
        _authorized_admin(
            authorization,
            x_admin_role,
            x_admin_id_digest,
            x_admin_session_digest,
            x_admin_auth_method,
            operation="connect_company_learning_folder",
        )
        result = ingest_folder(payload.folder_path)
        job = _JOB_STORE.create_completed(result)
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    except CompanyLearningIngestError as exc:
        raise HTTPException(status_code=422, detail=_error_detail(exc.fail_class)) from exc
    return {
        "schema_version": "company_learning.connect.response.v1",
        "job_id": job.job_id,
        "status": job.status,
        "folder_digest": job.folder_digest,
        "ingest_digest": job.ingest_digest,
        "counters": job.public_status()["counters"],
        "raw_text_logged": False,
        "external_send_zero": True,
    }


@router.get("/v1/company-learning/status")
async def company_learning_status(
    request: Request,
    job_id: str = Query(..., min_length=1),
    authorization: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        _verify_localhost(request)
        _authorized_admin(
            authorization,
            x_admin_role,
            x_admin_id_digest,
            x_admin_session_digest,
            x_admin_auth_method,
            operation="company_learning_status",
        )
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    job = _JOB_STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=_error_detail("JOB_NOT_FOUND"))
    return job.public_status()


@router.get("/v1/company-learning/understanding")
async def company_learning_understanding(
    request: Request,
    job_id: str = Query(..., min_length=1),
    authorization: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        _verify_localhost(request)
        _authorized_admin(
            authorization,
            x_admin_role,
            x_admin_id_digest,
            x_admin_session_digest,
            x_admin_auth_method,
            operation="company_learning_understanding",
        )
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    job = _JOB_STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=_error_detail("JOB_NOT_FOUND"))
    return build_understanding(job, llm_status=_llm_status())


@router.post("/v1/company-learning/handoff")
async def company_learning_handoff(
    payload: CompanyLearningHandoffRequest,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_id_digest: Optional[str] = Header(default=None),
    x_admin_session_digest: Optional[str] = Header(default=None),
    x_admin_auth_method: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    try:
        _verify_localhost(request)
        _authorized_admin(
            authorization,
            x_admin_role,
            x_admin_id_digest,
            x_admin_session_digest,
            x_admin_auth_method,
            operation="company_learning_handoff",
        )
    except AdminAuthError as exc:
        raise HTTPException(status_code=403, detail=admin_error_payload(exc)) from exc
    job = _JOB_STORE.get(payload.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=_error_detail("JOB_NOT_FOUND"))

    understanding = build_understanding(job, llm_status=_llm_status())
    if understanding.get("needs_review") is True and not payload.admin_confirmed_needs_review:
        raise HTTPException(status_code=409, detail=_error_detail("NEEDS_REVIEW_CONFIRMATION_REQUIRED"))

    if understanding.get("needs_review") is True and payload.admin_confirmed_needs_review:
        with job.lock:
            job.understanding = {**understanding, "needs_review": False, "needs_review_reason": None}

    result = create_company_learning_candidate(
        job,
        store=_LEARNING_EVENT_STORE,
        llm_status=_llm_status(),
    )
    if result.event is None:
        status = 409 if result.fail_class in {"UNDERSTANDING_NEEDS_REVIEW", "LEARNING_EVENT_ALREADY_EXISTS"} else 422
        raise HTTPException(status_code=status, detail=_error_detail(result.fail_class or "HANDOFF_FAILED"))
    event = result.event
    return {
        "schema_version": "company_learning.handoff.response.v1",
        "job_id": job.job_id,
        "learning_event_id": event["learning_event_id"],
        "status": event["status"],
        "learning_type": event["learning_type"],
        "approved_text_ref": event["approved_text_ref"],
        "approved_text_digest": event["approved_text_digest"],
        "sanitized_summary_digest": event["sanitized_summary_digest"],
        "verified_for_training": event["verified_for_training"],
        "policy_decision": event["policy_approval"]["decision"],
        "raw_text_logged": False,
        "external_send_zero": True,
    }
