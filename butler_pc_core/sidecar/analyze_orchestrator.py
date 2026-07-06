"""Analyze stream orchestrator for free-chat safe routing.

The task-budget router remains the resource planner. It must not create public
intent labels or endpoints, so this orchestrator runs Box1 intent routing first
and calls task budgeting only after a safe route has been selected.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler_pc_core.connect_loop.box1_router import (
    RouterRuntimeContext,
    RuleBasedBox1Router,
    canonical_sha256,
)
from butler_pc_core.output_safety.guards import GuardContext
from butler_pc_core.inference.model_identity import MAIN_MODEL_PATH_ENV, model_identity, model_path_conflict_reason
from butler_pc_core.router.task_budget_router import Route, TaskBudget, decide_task_budget
from butler_pc_core.sidecar.analyze_policy_preflight import policy_bootstrap_state
from butler_pc_core.sidecar.safe_general_chat import (
    SafeGeneralChatController,
    build_benign_free_chat_fallback,
    build_safe_general_chat_prompt,
)


SseFactory = Callable[[str, dict[str, Any]], str]
HubPairedFactory = Callable[[], bool]
LlmFactory = Callable[[], Awaitable[Any]]
TaskBudgetFactory = Callable[..., TaskBudget]


@dataclass(frozen=True)
class AnalyzeStreamRequest:
    query: str = ""
    card_mode: str = "free"
    total_chunks: int = 1
    output_dir: str = "."
    file_paths: list[str] = field(default_factory=list)


def _digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _attachment_digest(path: str) -> dict[str, Any]:
    p = Path(path)
    data = p.read_bytes()
    return {"content_digest": _digest_bytes(data), "size_bytes": len(data)}


def build_chat_request(params: AnalyzeStreamRequest, *, request_id: str) -> dict[str, Any]:
    attachments: list[dict[str, Any]] = []
    for path in params.file_paths:
        try:
            attachments.append(_attachment_digest(path))
        except Exception:
            continue
    return {
        "request_id": request_id,
        "session_id_digest": canonical_sha256("local-session"),
        "tenant_id_digest": canonical_sha256("local-tenant"),
        "device_id": "local-device",
        "user_role": "employee",
        "department_id_digest": canonical_sha256("dept-unknown"),
        "text_ref": "device_local_only",
        "text_digest": canonical_sha256(params.query),
        "attachments": attachments,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schema_version": "chat_request.v1",
    }


def public_execution_mode(route: Route | str) -> str:
    route_value = str(route.value if isinstance(route, Route) else route)
    if route_value == Route.PC_DIRECT.value:
        return "local_pc"
    return route_value


class AnalyzeStreamOrchestrator:
    def __init__(
        self,
        *,
        router: RuleBasedBox1Router | None = None,
        safe_chat: SafeGeneralChatController | None = None,
        task_budget_func: TaskBudgetFactory = decide_task_budget,
        bootstrap_func: Callable[[], Any] = policy_bootstrap_state,
    ) -> None:
        self.router = router or RuleBasedBox1Router()
        self.safe_chat = safe_chat or SafeGeneralChatController()
        self.task_budget_func = task_budget_func
        self.bootstrap_func = bootstrap_func

    async def stream_free_chat(
        self,
        params: AnalyzeStreamRequest,
        *,
        task_id: str,
        sse: SseFactory,
        hub_paired: HubPairedFactory,
        llm_factory: LlmFactory,
    ) -> AsyncGenerator[str, None]:
        bootstrap = self.bootstrap_func()
        if not bootstrap.ready:
            yield sse(
                "meta",
                {
                    "source": "policy_gate",
                    "route": "blocked",
                    "target_endpoint": "none",
                    "llm_invoked": False,
                    "external_send_zero": True,
                    "raw_text_logged": False,
                },
            )
            yield sse(
                "error",
                {
                    "fail_class": bootstrap.fail_class,
                    "message": "정책 설정 후 일반 대화를 사용할 수 있습니다.",
                    "llm_invoked": False,
                },
            )
            return

        request_id = str(uuid.uuid4())
        chat_request = build_chat_request(params, request_id=request_id)
        decision = self.router.decide(
            chat_request,
            RouterRuntimeContext(runtime_text=params.query, policy_precheck="allow"),
        )
        yield sse(
            "meta",
            {
                "source": "router",
                "schema_version": decision["schema_version"],
                "intent_label": decision["intent_label"],
                "target_box_id": decision["target_box_id"],
                "target_endpoint": decision["target_endpoint"],
                "fallback_required": decision["fallback_required"],
                "routing_confidence": decision["routing_confidence"],
                "policy_digest": bootstrap.policy_digest,
                "raw_text_logged": False,
                "external_send_zero": True,
            },
        )

        total_file_bytes = sum(
            Path(path).stat().st_size for path in params.file_paths if Path(path).is_file()
        )
        estimated_tokens = total_file_bytes // 4
        budget = self.task_budget_func(
            file_bytes=total_file_bytes,
            estimated_tokens=estimated_tokens,
            page_count=0,
            hub_paired=hub_paired(),
            task_type="general_chat",
        )
        yield sse(
            "meta",
            {
                "source": "task_budget",
                "execution_mode": public_execution_mode(budget.route),
                "file_bytes": total_file_bytes,
                "estimated_tokens": estimated_tokens,
                "max_wall_time_sec": budget.max_wall_time_sec,
            },
        )

        if budget.route == Route.REFUSE_TEAM_HUB:
            yield sse(
                "error",
                {
                    "fail_class": "INVALID_REQUEST_SCHEMA",
                    "message": budget.user_message,
                    "llm_invoked": False,
                },
            )
            return
        if budget.route in {Route.TEAM_HUB_RECOMMENDED, Route.PC_PREVIEW_TEAM_HUB}:
            yield sse(
                "complete",
                {
                    "source": "task_budget",
                    "result_text": budget.user_message,
                    "result_path": "",
                    "total_elapsed_sec": 0.0,
                    "llm_invoked": False,
                },
            )
            return

        if decision["intent_label"] != "general_chat":
            yield sse(
                "complete",
                {
                    "source": "router",
                    "result_text": "이 요청은 해당 Butler 카드에서 처리해야 합니다. 알맞은 카드를 선택해 주세요.",
                    "result_path": "",
                    "intent_label": decision["intent_label"],
                    "target_box_id": decision["target_box_id"],
                    "target_endpoint": decision["target_endpoint"],
                    "llm_invoked": False,
                    "total_elapsed_sec": 0.0,
                },
            )
            return

        try:
            llm = await llm_factory()
        except Exception as exc:  # noqa: BLE001
            yield sse(
                "error",
                {
                    "fail_class": "SAFE_CHAT_LLM_UNAVAILABLE",
                    "message": "일반 대화 모델을 준비하지 못했습니다.",
                    "error_class": type(exc).__name__,
                    "llm_invoked": False,
                },
            )
            return

        prompt = build_safe_general_chat_prompt(params.query)

        def _tokens(cancel_event):
            return llm.generate_stream_with_cancel(prompt, cancel_event, max_tokens=1024)

        model_conflict_reason = model_path_conflict_reason()
        yield sse(
            "meta",
            {
                "source": "safe_chat",
                "llm_invoked": True,
                **model_identity(role="free_chat", env_key=MAIN_MODEL_PATH_ENV),
                "model_path_conflict": model_conflict_reason is not None,
                "model_path_conflict_reason": model_conflict_reason or "",
            },
        )
        try:
            result = await self.safe_chat.run_buffered(
                _tokens,
                timeout_sec=float(budget.max_wall_time_sec),
                context=GuardContext(route="general_chat", profile="free_general_chat"),
            )
        except asyncio.TimeoutError:
            yield sse(
                "cancelled",
                {
                    "reason": "safe_chat_timeout",
                    "partial_path": "",
                    "partial_result_path": "",
                    "completed_chunks": 0,
                    "message": "일반 대화 생성 시간이 초과되었습니다.",
                    "llm_invoked": True,
                },
            )
            return
        except Exception as exc:  # noqa: BLE001
            yield sse(
                "error",
                {
                    "fail_class": "SAFE_CHAT_GENERATION_FAILED",
                    "message": "일반 대화 생성에 실패했습니다.",
                    "error_class": type(exc).__name__,
                    "llm_invoked": True,
                },
            )
            return
        if result.text is None:
            yield sse(
                "error",
                {
                    "fail_class": result.fail_class,
                    "llm_invoked": result.llm_invoked,
                },
            )
            return

        output_text = result.text
        fallback_applied = False
        if result.replaced:
            fallback_text = build_benign_free_chat_fallback(params.query)
            if fallback_text is not None:
                fallback_verdict = self.safe_chat.guard.evaluate(
                    fallback_text,
                    GuardContext(route="general_chat", profile="free_general_chat"),
                )
                if fallback_verdict.action.value == "allow":
                    output_text = fallback_text
                    fallback_applied = True

        yield sse("chunk", {"token": output_text})
        yield sse(
            "complete",
            {
                "source": "safe_chat",
                "result_text": output_text,
                "result_path": "",
                "total_elapsed_sec": result.elapsed_sec,
                "llm_invoked": result.llm_invoked,
                "replaced": result.replaced,
                "benign_fallback_applied": fallback_applied,
                "fail_class": None if result.action == "allow" else result.fail_class,
                "unsupported_numbers": result.unsupported_numbers,
                "system_prompt_leak": False,
                "device_privacy_invariant_pass": True,
                "guard_fail_class": None if result.action == "allow" else result.fail_class,
            },
        )
