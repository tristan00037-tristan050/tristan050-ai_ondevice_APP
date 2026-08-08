from __future__ import annotations

import re
from typing import Any, Callable

from fastapi.responses import JSONResponse

from .contracts import ContractValidationError, sha256_text
from .policy_gate import PolicyGate, build_policy_task_envelope
from .storage import PolicyLoadError, PolicyStore
from butler_pc_core.learning_capability.consumer_bindings import (
    default_consumer_binding_store,
)

_LOCAL_UI_ORIGINS = frozenset({
    "tauri://localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
})

DEFAULT_ROUTE_OPERATION: dict[str, tuple[str, str]] = {
    "/v1/helpers/1/search": ("helper1", "memory_search"),
    # helper1 `/v1/helpers/1/ask` 라우트 누락 정정 (fix(policy): helper1/ask PolicyGate 포함):
    # search 와 동일 사이드카 모듈에서 등록되며 동일한 메모리 자산을 사용하지만 ask 는
    # chat-form 응답 — PolicyGate 적용 누락 시 정책·테넌트·외부전송 검증이 우회되어
    # fail-closed 의무 위반. 본 라인 추가로 모든 박스/헬퍼 진입 라우트가 중앙 게이트 1벌
    # 으로 평가된다.
    "/v1/helpers/1/ask": ("helper1", "memory_ask"),
    "/v1/cards/2/rewrite": ("2", "form_convert"),
    "/v1/cards/3/draft": ("3", "draft_write"),
    "/accounting/classify": ("5", "accounting_classify"),
}

_ACCOUNTING_ASSIGNMENT_MUTATION_RE = re.compile(
    r"^/v1/accounting/(?:unaccounted/[A-Za-z0-9_-]{16,128}/(?:assign|action-nonce)|"
    r"learned-rules/[A-Za-z0-9_-]{16,128}/deactivate|"
    r"rule-conflicts/[A-Za-z0-9_-]{16,128}/resolve|"
    r"review/(?:transactions/[A-Za-z0-9_-]{16,128}/rule-application/revert|"
    r"batches/[A-Za-z0-9_-]{16,128}/quarantine/[A-Za-z0-9-]{36}/recompile))$"
)


def _route_operation(path: str, routes: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    exact = routes.get(path)
    if exact is not None:
        return exact
    if _ACCOUNTING_ASSIGNMENT_MUTATION_RE.fullmatch(path):
        # Assignment is not journal posting, but it consumes the same Box5
        # company-policy envelope as classification until a versioned policy
        # operation registry adds a narrower accounting_review operation.
        return ("5", "accounting_classify")
    return None


def _is_accounting_route(path: str) -> bool:
    # 정책 결정 속성을 서버 고정 안전값으로 강제하는 대상은 회계검토 assignment '변경' 경로다.
    # /accounting/classify(분류 SSE)는 mutation 이 아니며 기존 정책 흐름을 보존한다(회귀 방지).
    return _ACCOUNTING_ASSIGNMENT_MUTATION_RE.fullmatch(path) is not None


def _header_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _policy_json_response(
    request: Any,
    *,
    status_code: int,
    content: dict[str, Any],
) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=content)
    origin = request.headers.get("origin")
    if origin in _LOCAL_UI_ORIGINS:
        response.headers["access-control-allow-origin"] = origin
        response.headers["vary"] = "Origin"
    return response


def add_policy_gate_middleware(
    app: Any,
    *,
    policy_store: PolicyStore | Callable[[], PolicyStore],
    route_operation: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Register central PolicyGate middleware before box/helper route execution.

    Box-level scattered policy checks are intentionally avoided.
    """

    routes = route_operation or DEFAULT_ROUTE_OPERATION

    @app.middleware("http")
    async def _company_policy_gate(request, call_next):  # type: ignore[no-untyped-def]
        operation_binding = _route_operation(request.url.path, routes)
        if request.method != "POST" or operation_binding is None:
            return await call_next(request)

        box_id, operation = operation_binding
        try:
            store = policy_store() if callable(policy_store) else policy_store
            policy = store.load_active_policy()
        except PolicyLoadError:
            return _policy_json_response(
                request,
                status_code=503,
                content={
                    "schema_version": "policy_gate_result.v1",
                    "allowed": False,
                    "decision": "block",
                    "block_reason": "POLICY_LOAD_FAILED",
                    "applied_policy_digest": None,
                    "audit_ref": sha256_text("POLICY_LOAD_FAILED"),
                    "external_send_zero": True,
                    "raw_text_logged": False,
                },
            )

        # ★ RI-P0-002/013: 회계검토(assignment/classify) 경로는 정책 결정에 영향을 주는
        # 권한·학습·보존·등급·외부전송 속성을 클라이언트 헤더에서 취하지 않는다. 클라이언트가
        # x-user-role: admin / x-learning-allowed: 1 등으로 정책을 조작하는 공격을 막기 위해
        # 서버 고정 안전값(최소 권한 employee·최고 보안 restricted·학습 불가·외부전송 0·마스킹)만
        # 사용한다. tenant/dept 스코프는 정책 매칭용이며, 실제 tenant 인증은 route 핸들러가
        # active company profile 로 별도 강제한다.
        accounting = _is_accounting_route(request.url.path)
        try:
            env = build_policy_task_envelope(
                request_id=request.headers.get("x-request-id") or "missing-request-id",
                tenant_digest=request.headers.get("x-tenant-digest") or sha256_text("tenant-local"),
                dept_digest=request.headers.get("x-dept-digest") or sha256_text("dept-unknown"),
                user_role="employee" if accounting else (request.headers.get("x-user-role") or "employee"),
                target_box_id=box_id,
                operation=operation,
                doc_grade="restricted" if accounting else (request.headers.get("x-doc-grade") or "restricted"),
                external_send_requested=False
                if accounting
                else _header_bool(request.headers.get("x-external-send-requested")),
                format_id=request.headers.get("x-format-id"),
                learning_allowed=False if accounting else _header_bool(request.headers.get("x-learning-allowed")),
                retention_days=30 if accounting else int(request.headers.get("x-retention-days") or 30),
                masking_requested=True if accounting else _header_bool(request.headers.get("x-masking-requested")),
            )
            gate = PolicyGate.evaluate(env, policy)
        except (ContractValidationError, ValueError):
            return _policy_json_response(
                request,
                status_code=403,
                content={
                    "schema_version": "policy_gate_result.v1",
                    "allowed": False,
                    "decision": "block",
                    "block_reason": "POLICY_ENVELOPE_INVALID",
                    "applied_policy_digest": None,
                    "audit_ref": sha256_text("POLICY_ENVELOPE_INVALID"),
                    "external_send_zero": True,
                    "raw_text_logged": False,
                },
            )

        if not gate.allowed:
            return _policy_json_response(request, status_code=403, content=gate.to_dict())

        response = await call_next(request)
        response.headers["x-policy-audit-ref"] = gate.audit_ref
        if gate.applied_policy_digest:
            response.headers["x-applied-policy-digest"] = gate.applied_policy_digest
            try:
                default_consumer_binding_store().record(
                    "company_policy",
                    gate.applied_policy_digest,
                    "PolicyGate.middleware.allowed_response.v1",
                )
            except Exception:
                # A failed proof write must never create an IN_USE claim, but it
                # also must not turn an already-authorized product request into
                # a new availability failure.
                pass
        return response
