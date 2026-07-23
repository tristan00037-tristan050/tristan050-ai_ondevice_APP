"""FastAPI product routes for Box5 accounting review and assignment."""

from __future__ import annotations

import re
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from butler_pc_core.auth.capability_token import (
    CapabilityTokenError,
    CapabilityTokenManager,
)
from butler_pc_core.company_profile.storage import CompanyProfileStore, ProfileLoadError

from .domain import (
    AssignCommand,
    AssignmentError,
    ConflictDecision,
    require_mutation_headers,
)
from .runtime import get_accounting_review_runtime
from butler_pc_core.accounting.classify.reconciliation_v2 import tenant_uuid


router = APIRouter()
_TOKEN_MANAGER = CapabilityTokenManager()
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class AssignmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    account_id: str
    scope: str
    registry_digest: str
    expected_transaction_version: int


class ConflictResolutionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    decision: ConflictDecision
    expected_conflict_version: int


class A4RunPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str


class A4ReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str


def _request_id(request: Request) -> str:
    candidate = request.headers.get("x-request-id")
    return (
        candidate
        if candidate and _REQUEST_ID_RE.fullmatch(candidate)
        else uuid.uuid4().hex
    )


def _problem(error: AssignmentError, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content=error.problem(request_id),
        media_type="application/problem+json",
    )


def _reject_external_origin(origin: str | None) -> None:
    if origin is None:
        return
    parsed = urlparse(origin)
    if parsed.scheme == "tauri" and parsed.hostname in {None, "localhost"}:
        return
    if parsed.scheme in {"http", "https"} and parsed.hostname in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        return
    raise AssignmentError(
        "AUTHORIZATION_DENIED", 403, "External origins cannot access accounting review."
    )


def _context(authorization: str | None, origin: str | None):
    _reject_external_origin(origin)
    try:
        _TOKEN_MANAGER.verify_authorization_header(authorization)
    except CapabilityTokenError as exc:
        status = 401 if "MISSING" in exc.fail_class.value else 403
        raise AssignmentError(
            "AUTHORIZATION_DENIED", status, "Accounting review authorization failed."
        ) from exc
    try:
        profile = CompanyProfileStore().load_active_profile()
    except ProfileLoadError as exc:
        raise AssignmentError(
            "BLOCK_SECURE_TRANSACTION_PROJECTION_UNAVAILABLE",
            503,
            "The active company profile could not be verified.",
        ) from exc
    return get_accounting_review_runtime().context_from_profile(profile)


@router.get("/v1/accounting/batches/{batch_id}/review-summary")
def review_summary(
    batch_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    rid = _request_id(request)
    try:
        return get_accounting_review_runtime().review_summary(
            _context(authorization, origin), batch_id
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.get("/v1/accounting/batches/{batch_id}/unaccounted")
def unaccounted_page(
    batch_id: str,
    request: Request,
    cursor: str | None = Query(default=None, max_length=512),
    page_size: int = Query(default=50, ge=1, le=100),
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    rid = _request_id(request)
    try:
        return get_accounting_review_runtime().unaccounted_page(
            _context(authorization, origin),
            batch_id,
            cursor=cursor,
            page_size=page_size,
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.get("/v1/accounting/chart-of-accounts")
def chart_of_accounts(
    request: Request,
    registry_digest: str | None = Query(default=None),
    locale: str = Query(default="ko-KR", min_length=2, max_length=32),
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    rid = _request_id(request)
    try:
        _context(authorization, origin)
        runtime = get_accounting_review_runtime()
        if registry_digest is not None:
            runtime.registry.require_digest(registry_digest)
        return runtime.registry.public_view(locale)
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.post("/v1/accounting/unaccounted/{txn_id}/assign")
def assign_account(
    txn_id: str,
    payload: AssignmentPayload,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    rid = _request_id(request)
    try:
        key, version = require_mutation_headers(idempotency_key, if_match)
        command = AssignCommand.from_dict(payload.model_dump(mode="json"))
        return get_accounting_review_runtime().assign(
            _context(authorization, origin),
            txn_id,
            command,
            idempotency_key=key,
            if_match_version=version,
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.get("/v1/accounting/learned-rules")
def learned_rules(
    request: Request,
    state: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    rid = _request_id(request)
    try:
        return get_accounting_review_runtime().learned_rules(
            _context(authorization, origin), state
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.post("/v1/accounting/learned-rules/{rule_id}/deactivate")
def deactivate_rule(
    rule_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    rid = _request_id(request)
    try:
        key, version = require_mutation_headers(idempotency_key, if_match)
        return get_accounting_review_runtime().deactivate_rule(
            _context(authorization, origin),
            rule_id,
            idempotency_key=key,
            if_match_version=version,
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.post("/v1/accounting/rule-conflicts/{conflict_id}/resolve")
def resolve_rule_conflict(
    conflict_id: str,
    payload: ConflictResolutionPayload,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    rid = _request_id(request)
    try:
        key, version = require_mutation_headers(idempotency_key, if_match)
        if (
            payload.schema_version != "2.0"
            or payload.expected_conflict_version != version
        ):
            raise AssignmentError(
                "CONFLICT_STALE",
                412,
                "The conflict version does not match If-Match.",
                current_version=payload.expected_conflict_version,
            )
        return get_accounting_review_runtime().resolve_conflict(
            _context(authorization, origin),
            conflict_id,
            decision=payload.decision,
            expected_conflict_version=payload.expected_conflict_version,
            idempotency_key=key,
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.get("/v1/accounting/review-capability")
def review_capability(
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    rid = _request_id(request)
    try:
        return get_accounting_review_runtime().capability(
            _context(authorization, origin)
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


def _a4_context(authorization: str | None, origin: str | None):
    context = _context(authorization, origin)
    return context, tenant_uuid(context.tenant_id)


@router.post("/box5/reconciliation/a4/runs")
def a4_run(
    payload: A4RunPayload,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    """Return the canonical run created by the actual accounting pipeline."""

    rid = _request_id(request)
    try:
        uuid.UUID(payload.run_id)
        _, tenant_id = _a4_context(authorization, origin)
        run = get_accounting_review_runtime().store.reconciliation_run(
            tenant_id, payload.run_id
        )
        if run is None:
            raise AssignmentError("A4_RUN_NOT_FOUND", 404, "A4 run is not available.")
        return {**run, "affects_reporting": False, "runtime_activation_allowed": False}
    except (AssignmentError, ValueError) as exc:
        error = (
            exc
            if isinstance(exc, AssignmentError)
            else AssignmentError("A4_RUN_INVALID", 422, "A4 run identifier is invalid.")
        )
        return _problem(error, rid)


@router.get("/box5/reconciliation/a4/runs/{run_id}")
def a4_get_run(
    run_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    return a4_run(A4RunPayload(run_id=run_id), request, authorization, origin)


@router.get("/box5/reconciliation/a4/runs/{run_id}/candidates")
def a4_candidates(
    run_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    rid = _request_id(request)
    try:
        uuid.UUID(run_id)
        _, tenant_id = _a4_context(authorization, origin)
        run = get_accounting_review_runtime().store.reconciliation_run(
            tenant_id, run_id
        )
        if run is None:
            raise AssignmentError("A4_RUN_NOT_FOUND", 404, "A4 run is not available.")
        return {
            "run_id": run_id,
            "items": get_accounting_review_runtime().store.reconciliation_candidates(
                tenant_id, run_id
            ),
            "affects_reporting": False,
        }
    except (AssignmentError, ValueError) as exc:
        error = (
            exc
            if isinstance(exc, AssignmentError)
            else AssignmentError("A4_RUN_INVALID", 422, "A4 run identifier is invalid.")
        )
        return _problem(error, rid)


@router.post("/box5/reconciliation/a4/runs/{run_id}/candidates/{edge_id}/review")
def a4_review_candidate(
    run_id: str,
    edge_id: str,
    payload: A4ReviewPayload,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    rid = _request_id(request)
    try:
        uuid.UUID(run_id)
        if not idempotency_key or not _REQUEST_ID_RE.fullmatch(idempotency_key):
            raise AssignmentError(
                "IDEMPOTENCY_KEY_REQUIRED", 400, "A valid idempotency key is required."
            )
        context, tenant_id = _a4_context(authorization, origin)
        return get_accounting_review_runtime().store.append_reconciliation_review(
            tenant_id=tenant_id,
            run_id=run_id,
            edge_id=edge_id,
            decision=payload.decision,
            actor_id=context.actor_id,
            idempotency_key=idempotency_key,
        )
    except (AssignmentError, ValueError) as exc:
        error = (
            exc
            if isinstance(exc, AssignmentError)
            else AssignmentError("A4_REVIEW_INVALID", 422, "A4 review is invalid.")
        )
        return _problem(error, rid)
