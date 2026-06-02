from __future__ import annotations

from typing import Any, Callable

from fastapi.responses import JSONResponse

from .contracts import ContractValidationError, sha256_text
from .policy_gate import PolicyGate, build_policy_task_envelope
from .storage import PolicyLoadError, PolicyStore

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


def _header_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def add_policy_gate_middleware(
    app: Any,
    *,
    policy_store: PolicyStore,
    route_operation: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Register central PolicyGate middleware before box/helper route execution.

    Box-level scattered policy checks are intentionally avoided.
    """

    routes = route_operation or DEFAULT_ROUTE_OPERATION

    @app.middleware("http")
    async def _company_policy_gate(request, call_next):  # type: ignore[no-untyped-def]
        if request.method != "POST" or request.url.path not in routes:
            return await call_next(request)

        box_id, operation = routes[request.url.path]
        try:
            policy = policy_store.load_active_policy()
        except PolicyLoadError:
            return JSONResponse(
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

        try:
            env = build_policy_task_envelope(
                request_id=request.headers.get("x-request-id") or "missing-request-id",
                tenant_digest=request.headers.get("x-tenant-digest") or sha256_text("tenant-local"),
                dept_digest=request.headers.get("x-dept-digest") or sha256_text("dept-unknown"),
                user_role=request.headers.get("x-user-role") or "employee",
                target_box_id=box_id,
                operation=operation,
                doc_grade=request.headers.get("x-doc-grade") or "restricted",
                external_send_requested=_header_bool(request.headers.get("x-external-send-requested")),
                format_id=request.headers.get("x-format-id"),
                learning_allowed=_header_bool(request.headers.get("x-learning-allowed")),
                retention_days=int(request.headers.get("x-retention-days") or 30),
                masking_requested=_header_bool(request.headers.get("x-masking-requested")),
            )
            gate = PolicyGate.evaluate(env, policy)
        except (ContractValidationError, ValueError):
            return JSONResponse(
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
            return JSONResponse(status_code=403, content=gate.to_dict())

        response = await call_next(request)
        response.headers["x-policy-audit-ref"] = gate.audit_ref
        if gate.applied_policy_digest:
            response.headers["x-applied-policy-digest"] = gate.applied_policy_digest
        return response
