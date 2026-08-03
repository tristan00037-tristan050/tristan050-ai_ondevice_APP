"""FastAPI product routes for Box5 accounting review and assignment."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from fastapi import APIRouter, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from butler_pc_core.auth.capability_token import CapabilityTokenError, CapabilityTokenManager
from butler_pc_core.company_profile.storage import CompanyProfileStore, ProfileLoadError

from .authorization import (
    Box5AuthorizationService,
    build_product_authorization_service,
)
from .domain import (
    AssignCommand,
    AssignmentError,
    AssignmentScope,
    ConflictDecision,
    require_mutation_headers,
    sha256_json,
)
from .runtime import AccountingReviewRuntime, get_accounting_review_runtime
from butler_pc_core.accounting.classify.reconciliation_v2 import tenant_uuid


router = APIRouter()
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_DEPENDENCY_STATE_KEY = "box5_accounting_dependencies"


@dataclass(frozen=True, slots=True)
class AccountingAssignmentDependencies:
    """Composition-root dependencies for every Box5 accounting endpoint.

    This object is intentionally installed on the FastAPI application rather
    than created as module globals.  The sidecar must share its one transport
    authenticator with these routes; a second token manager would make the
    product path impossible to authenticate while isolated route tests pass.
    """

    ipc_authenticator: CapabilityTokenManager
    authorization_service: Box5AuthorizationService
    profile_store_factory: Callable[[], CompanyProfileStore]
    runtime_provider: Callable[[], AccountingReviewRuntime]


def install_product_accounting_dependencies(
    app: FastAPI,
    ipc_authenticator: CapabilityTokenManager,
) -> None:
    """Install the fixed product composition without injectable trust inputs.

    Production trust remains pinned inside ``build_product_authorization_service``.
    Tests that need a synthetic issuer must build a separate application and
    install an explicit test dependency object; this function deliberately has
    no verifier, key, trust-policy, role, or capability override.
    """

    if hasattr(app.state, _DEPENDENCY_STATE_KEY):
        raise RuntimeError("BOX5_ACCOUNTING_DEPENDENCIES_ALREADY_INSTALLED")
    setattr(
        app.state,
        _DEPENDENCY_STATE_KEY,
        AccountingAssignmentDependencies(
            ipc_authenticator=ipc_authenticator,
            authorization_service=build_product_authorization_service(
                ipc_authenticator
            ),
            profile_store_factory=CompanyProfileStore,
            runtime_provider=get_accounting_review_runtime,
        ),
    )


def _dependencies(request: Request) -> AccountingAssignmentDependencies:
    dependencies = getattr(request.app.state, _DEPENDENCY_STATE_KEY, None)
    if not isinstance(dependencies, AccountingAssignmentDependencies):
        raise AssignmentError(
            "PRODUCT_COMPOSITION_UNAVAILABLE",
            503,
            "The accounting authorization boundary is not installed.",
        )
    return dependencies


def _runtime(request: Request) -> AccountingReviewRuntime:
    return _dependencies(request).runtime_provider()


class AssignmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    scope: str
    client_action_id: str
    user_action_nonce: str
    expected_transaction_version: int


class QuarantineCorrectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_minor: int | None = None
    booked_date: str | None = None
    currency: str | None = None


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
    existing = getattr(request.state, "box5_request_id", None)
    if isinstance(existing, str) and _REQUEST_ID_RE.fullmatch(existing):
        return existing
    candidate = request.headers.get("x-request-id")
    request_id = (
        candidate
        if candidate and _REQUEST_ID_RE.fullmatch(candidate)
        else uuid.uuid4().hex
    )
    request.state.box5_request_id = request_id
    return request_id


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


def _context(
    request: Request,
    authorization: str | None,
    origin: str | None,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
):
    dependencies = _dependencies(request)
    try:
        profile = dependencies.profile_store_factory().load_active_profile()
    except ProfileLoadError as exc:
        raise AssignmentError(
            "BLOCK_SECURE_TRANSACTION_PROJECTION_UNAVAILABLE",
            503,
            "The active company profile could not be verified.",
        ) from exc
    try:
        _reject_external_origin(origin)
        if action == "ACCOUNTING_REVIEW_VIEW":
            # UA2 is intentionally a six-write assertion contract. Read-only
            # review routes still require the local IPC session but do not mint
            # or consume a human mutation assertion.
            session = dependencies.authorization_service.verify_transport(authorization)
            return _runtime(request).context_from_profile(
                profile, session, action=action
            )
        return dependencies.authorization_service.authorize(
            authorization=authorization,
            user_authorization=request.headers.get("butler-user-authorization"),
            profile=profile,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=_request_id(request),
        )
    except AssignmentError as error:
        if action != "ACCOUNTING_REVIEW_VIEW":
            _runtime(request).store.append_authorization_denial(
                tenant_id=str(profile.profile_id),
                company_id=str(profile.profile_digest),
                action=action,
                resource_id=resource_id,
                reason_code=error.code,
                request_id=_request_id(request),
                policy_digest=dependencies.authorization_service.audit_policy_digest,
            )
        raise


def _assignment_action(scope: AssignmentScope) -> str:
    if scope is AssignmentScope.THIS_ONLY:
        return "ASSIGNMENT_CREATE"
    return "RULE_FUTURE_CREATE"


@router.get("/v1/accounting/batches/{batch_id}/review-summary")
def review_summary(
    batch_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    rid = _request_id(request)
    try:
        return _runtime(request).review_summary(
            _context(
                request,
                authorization,
                origin,
                action="ACCOUNTING_REVIEW_VIEW",
                resource_type="REVIEW_BATCH",
                resource_id=batch_id,
            ),
            batch_id,
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
        return _runtime(request).unaccounted_page(
            _context(
                request,
                authorization,
                origin,
                action="ACCOUNTING_REVIEW_VIEW",
                resource_type="REVIEW_BATCH",
                resource_id=batch_id,
            ),
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
        _context(
            request,
            authorization,
            origin,
            action="ACCOUNTING_REVIEW_VIEW",
            resource_type="REVIEW_BATCH",
            resource_id=registry_digest or "active-registry",
        )
        runtime = _runtime(request)
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
        return _runtime(request).assign(
            _context(
                request,
                authorization,
                origin,
                action=_assignment_action(command.scope),
                resource_type="ACCOUNTING_TRANSACTION",
                resource_id=txn_id,
            ),
            txn_id,
            command,
            idempotency_key=key,
            if_match_version=version,
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.post("/v1/accounting/unaccounted/{txn_id}/action-nonce")
def issue_assignment_nonce(
    txn_id: str,
    request: Request,
    scope: AssignmentScope = Query(...),
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    rid = _request_id(request)
    try:
        return _runtime(request).issue_assignment_nonce(
            _context(
                request,
                authorization,
                origin,
                action=_assignment_action(scope),
                resource_type="ACCOUNTING_TRANSACTION",
                resource_id=txn_id,
            ),
            txn_id,
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.get("/v1/accounting/review/batches/{batch_id}/quarantine")
def quarantine_page(
    batch_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
):
    rid = _request_id(request)
    try:
        return _runtime(request).quarantine_page(
            _context(
                request,
                authorization,
                origin,
                action="ACCOUNTING_REVIEW_VIEW",
                resource_type="REVIEW_BATCH",
                resource_id=batch_id,
            ),
            batch_id,
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.post("/v1/accounting/review/batches/{batch_id}/quarantine/{row_id}/recompile")
def recompile_quarantine(
    batch_id: str,
    row_id: str,
    payload: QuarantineCorrectionPayload,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    rid = _request_id(request)
    try:
        key, version = require_mutation_headers(idempotency_key, if_match)
        correction = {
            key_name: value
            for key_name, value in payload.model_dump(mode="json").items()
            if value is not None
        }
        return _runtime(request).recompile_quarantine(
            _context(
                request,
                authorization,
                origin,
                action="QUARANTINE_ROW_RECOMPILE",
                resource_type="QUARANTINED_ROW",
                resource_id=row_id,
            ),
            batch_id,
            row_id,
            correction,
            expected_version=version,
            idempotency_key=key,
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
        return _runtime(request).learned_rules(
            _context(
                request,
                authorization,
                origin,
                action="ACCOUNTING_REVIEW_VIEW",
                resource_type="LEARNED_RULE",
                resource_id=state or "all-rules",
            ),
            state,
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
        return _runtime(request).deactivate_rule(
            _context(
                request,
                authorization,
                origin,
                action="RULE_DEACTIVATE",
                resource_type="LEARNED_RULE",
                resource_id=rule_id,
            ),
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
        return _runtime(request).resolve_conflict(
            _context(
                request,
                authorization,
                origin,
                action="CONFLICT_RESOLVE",
                resource_type="RULE_CONFLICT",
                resource_id=conflict_id,
            ),
            conflict_id,
            decision=payload.decision,
            expected_conflict_version=payload.expected_conflict_version,
            idempotency_key=key,
        )
    except AssignmentError as exc:
        return _problem(exc, rid)


@router.post("/v1/accounting/review/transactions/{txn_id}/rule-application/revert")
def revert_rule_application(
    txn_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    rid = _request_id(request)
    try:
        key, version = require_mutation_headers(idempotency_key, if_match)
        return _runtime(request).revert_rule_application(
            _context(
                request,
                authorization,
                origin,
                action="RULE_APPLICATION_REVERT",
                resource_type="ACCOUNTING_TRANSACTION",
                resource_id=txn_id,
            ),
            txn_id,
            expected_version=version,
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
        _reject_external_origin(origin)
        dependencies = _dependencies(request)
        dependencies.authorization_service.verify_transport(authorization)
        try:
            profile = dependencies.profile_store_factory().load_active_profile()
        except ProfileLoadError as exc:
            raise AssignmentError(
                "BLOCK_SECURE_TRANSACTION_PROJECTION_UNAVAILABLE",
                503,
                "The active company profile could not be verified.",
            ) from exc
        runtime = dependencies.runtime_provider()
        payload = runtime.capability(runtime.context_from_profile(profile))
        if not dependencies.authorization_service.authority_available:
            payload["status"] = "UNAVAILABLE"
            payload["self_test"] = "FAIL"
            payload["reason_codes"] = sorted(
                set(payload["reason_codes"] + ["BLOCK_HUMAN_AUTHORITY_UNRESOLVED"])
            )
            payload["evidence_digest"] = sha256_json(
                {key: value for key, value in payload.items() if key != "evidence_digest"}
            )
        return payload
    except AssignmentError as exc:
        return _problem(exc, rid)


def _a4_context(
    request: Request,
    authorization: str | None,
    origin: str | None,
    *,
    resource_id: str,
):
    # A4 is an existing, separately attested reconciliation boundary. Preserve
    # its transport-only compatibility contract; the new Box5 user-assignment
    # authority must not silently rewrite or disable that independent track.
    _reject_external_origin(origin)
    dependencies = _dependencies(request)
    try:
        dependencies.ipc_authenticator.verify_authorization_header(authorization)
    except CapabilityTokenError as exc:
        status = 401 if "MISSING" in exc.fail_class.value else 403
        raise AssignmentError(
            "AUTHORIZATION_DENIED", status, "A4 transport authorization failed."
        ) from exc
    try:
        profile = dependencies.profile_store_factory().load_active_profile()
    except ProfileLoadError as exc:
        raise AssignmentError(
            "BLOCK_SECURE_TRANSACTION_PROJECTION_UNAVAILABLE",
            503,
            "The active company profile could not be verified.",
        ) from exc
    context = dependencies.runtime_provider().context_from_profile(profile)
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
        _, tenant_id = _a4_context(
            request, authorization, origin, resource_id=payload.run_id
        )
        run = _runtime(request).store.reconciliation_run(
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
        _, tenant_id = _a4_context(
            request, authorization, origin, resource_id=run_id
        )
        runtime = _runtime(request)
        run = runtime.store.reconciliation_run(
            tenant_id, run_id
        )
        if run is None:
            raise AssignmentError("A4_RUN_NOT_FOUND", 404, "A4 run is not available.")
        return {
            "run_id": run_id,
            "items": runtime.store.reconciliation_candidates(tenant_id, run_id),
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
        context, tenant_id = _a4_context(
            request, authorization, origin, resource_id=run_id
        )
        return _runtime(request).store.append_reconciliation_review(
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
