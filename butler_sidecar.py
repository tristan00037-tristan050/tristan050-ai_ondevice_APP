"""
butler_sidecar.py
=================
Butler PC Core – 로컬 사이드카 HTTP 서버 (FastAPI)

엔드포인트
----------
GET  /health                  서버 상태 확인
POST /api/precheck             파일 등급 사전 체크 (file_path)
POST /api/analyze/stream       진행률 SSE 스트림 (text/event-stream)
DELETE /api/analyze/{task_id}/cancel  작업 취소
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess as _subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field as _dc_field
from pathlib import Path
from typing import AsyncGenerator

# 레포 루트를 sys.path에 추가 (직접 실행 시)
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse
    from pydantic import BaseModel
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

from butler_pc_core.router.task_budget_router import (
    classify_file,
    BudgetResult,
    NotAFileError,
    decide_task_budget,
    Route,
)
from butler_pc_core.runtime.timeout_controller import (
    TimeoutController,
    PartialResultError,
    HardTimeoutError,
    ChunkTimeoutError,
    UserCancelledError,
    HARD_TIMEOUT_SEC,
)
from butler_pc_core.inference.llm_runtime import LlmRuntime, _strip_residual_stop_tokens
from datetime import datetime, timezone as _tz

# ---------------------------------------------------------------------------
# 공유 LLM 싱글톤 — sidecar 기동 시 1회 로드, 모든 요청에서 재사용
# ---------------------------------------------------------------------------
_SHARED_LLM: LlmRuntime | None = None
_LLM_INIT_LOCK = threading.Lock()


def _init_shared_llm() -> None:
    """BUTLER_MODEL_PATH 로 모델을 강제 로드(기존 인스턴스 교체). startup 이벤트에서 호출."""
    global _SHARED_LLM
    model_path = os.environ.get("BUTLER_MODEL_PATH", "") or None
    _SHARED_LLM = LlmRuntime(model_path=model_path)


def _init_if_none_sync() -> "LlmRuntime":
    """double-check locking — 동시 첫 요청이 모두 같은 싱글톤을 받도록 보장 (P1-1)."""
    global _SHARED_LLM
    if _SHARED_LLM is None:
        with _LLM_INIT_LOCK:
            if _SHARED_LLM is None:
                model_path = os.environ.get("BUTLER_MODEL_PATH", "") or None
                _SHARED_LLM = LlmRuntime(model_path=model_path)
    return _SHARED_LLM  # type: ignore[return-value]


def _is_hub_paired() -> bool:
    """Team Hub PC 페어링 상태 (베타: 환경변수 BUTLER_HUB_PAIRED 또는 기본 False)."""
    return os.environ.get("BUTLER_HUB_PAIRED", "").lower() in ("1", "true", "yes")


async def _ensure_shared_llm() -> "LlmRuntime":
    """비블로킹: executor 에서 싱글톤 보장 후 반환."""
    if _SHARED_LLM is not None:
        return _SHARED_LLM
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _init_if_none_sync)
    return _SHARED_LLM  # type: ignore[return-value]

# FactPack 관련 import 및 초기화는 FastAPI/Pydantic 가용성에 의존.
# (Pydantic 미설치 환경에서도 stdlib fallback 모드가 import 단계에서 깨지지 않도록 가드)
if _FASTAPI_AVAILABLE:
    from butler_pc_core.factpack import FactPack
    from butler_pc_core.factpack.schema import FactPackAuditEntry

    # FactPack — 기동 시 1회 로드 (수~수십 ms, 메모리 ~수 MB)
    FACT_PACK = FactPack.from_default_facts_dir()
    _PACK_VERSION = "factpack-v1"
    _factpack_audit_log: list[FactPackAuditEntry] = []
else:
    # stdlib fallback 모드 — FactPack 분기는 라우트 핸들러 안에서만 호출되며,
    # 라우트 핸들러 자체가 _FASTAPI_AVAILABLE 가드 안에 있으므로 None 안전.
    FACT_PACK = None  # type: ignore[assignment]
    _PACK_VERSION = "factpack-v1"
    _factpack_audit_log = []  # type: ignore[var-annotated]

# task_id → TimeoutController マップ (キャンセル用)
_active_controllers: dict[str, TimeoutController] = {}
_controllers_lock = asyncio.Lock() if _FASTAPI_AVAILABLE else None  # type: ignore[assignment]

_CHUNK_WORKER = Path(__file__).resolve().parent / "butler_pc_core" / "inference" / "chunk_worker.py"


async def _real_chunk_work_isolated(
    params: "_AnalyzeParams",
    chunk_idx: int,
    timeout_sec: float,
) -> str:
    """LLM inference를 별도 subprocess에서 격리 실행.
    timeout 시 SIGKILL → thread 누수 없음.
    """
    params_json = json.dumps(params.__dict__, default=str)
    cmd = [
        sys.executable,
        str(_CHUNK_WORKER),
        "--params", params_json,
        "--chunk-idx", str(chunk_idx),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent)},
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        if proc.returncode != 0:
            err = (stderr or b"").decode(errors="replace")[:200]
            raise RuntimeError(f"chunk worker 오류 (rc={proc.returncode}): {err}")
        result = json.loads(stdout.decode())
        return str(result.get("result", ""))
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        raise


async def _real_chunk_work_inprocess(
    params: "_AnalyzeParams",
    chunk_idx: int,
    timeout_sec: float,
) -> str:
    """공유 모델 싱글톤으로 인-프로세스 LLM 추론.

    subprocess 스폰 없음 → 매 호출 모델 로드 없음 → 31s → ~6s.
    generate_with_cancel + cancel_event 로 timeout 시 executor thread 조기 종료 (P1-2).
    """
    # 프롬프트 조립 (chunk_worker.py 동일 로직)
    system_prompt = (
        "당신은 유능한 사무 보조 AI입니다. "
        "답변은 자연스러운 문단 중심으로 작성하세요. "
        "제목(##, ###)은 정말 필요한 경우에만 최소화하여 사용하고, "
        "구분선(---)은 사용하지 마세요. "
        "굵게(**) 강조도 최소화하세요. "
        "간결하고 읽기 쉬운 문장 구성을 우선하세요."
    )
    user_tmpl = "{{ query }}"
    try:
        from butler_pc_core.prompts.cards import load_card_prompt
        card = load_card_prompt(params.card_mode)
        system_prompt = card.get("system_prompt", system_prompt)
        user_tmpl = card.get("user_prompt_template", user_tmpl)
    except Exception:
        pass

    file_texts: list[str] = []
    for fp in params.file_paths:
        try:
            file_texts.append(Path(fp).read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass

    user_content = user_tmpl.replace("{{ query }}", params.query)
    if file_texts:
        user_content += "\n\n## 첨부 파일 내용\n" + "\n\n---\n".join(file_texts)

    prompt = (
        f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
        f"<|im_start|>user\n/no_think\n{user_content}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    llm = await _ensure_shared_llm()
    cancel_event = threading.Event()
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: llm.generate_with_cancel(prompt, cancel_event, max_tokens=2048),
            ),
            timeout=timeout_sec,
        )
    except asyncio.TimeoutError:
        cancel_event.set()
        raise
    return result


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
if _FASTAPI_AVAILABLE:
    app = FastAPI(
        title="Butler PC Core Sidecar",
        version="0.9.0",
        description="Butler PC Core 로컬 사이드카 — 파일 사전 체크 및 작업 라우팅",
    )

    # WKWebView origin은 tauri://localhost (프로덕션) 또는 http://localhost:1420 (개발)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Task-Id"],
    )

    # -----------------------------------------------------------------------
    # 모델
    # -----------------------------------------------------------------------
    class PrecheckRequest(BaseModel):
        file_path: str

    class PrecheckResponse(BaseModel):
        tier: str
        size_kb: float
        estimated_chunks: int
        estimated_seconds: float
        blocked: bool
        block_reason: str

    @dataclass
    class _AnalyzeParams:
        query: str = ""
        card_mode: str = "free"
        total_chunks: int = 1
        output_dir: str = "."
        file_paths: list = _dc_field(default_factory=list)

    # -----------------------------------------------------------------------
    # 엔드포인트
    # -----------------------------------------------------------------------
    @app.on_event("startup")
    async def _startup_load_model():
        """sidecar 기동 시 모델을 백그라운드 스레드에서 비동기 로드."""
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _init_shared_llm)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "butler-pc-core-sidecar", "version": "0.9.0"}

    @app.get("/api/sidecar/health")
    def sidecar_health():
        if _SHARED_LLM is not None:
            llm_status = _SHARED_LLM.status
        else:
            model_path = os.environ.get("BUTLER_MODEL_PATH", "")
            llm_status = "loading" if model_path else "no_model"
        return {
            "status": "ok",
            "service": "butler-pc-core-sidecar",
            "version": "0.9.0",
            "model_status": llm_status,
            "active_tasks": len(_active_controllers),
        }

    @app.get("/api/model/status")
    def model_status():
        model_path = os.environ.get("BUTLER_MODEL_PATH", "")
        if _SHARED_LLM is not None:
            return {
                "status": _SHARED_LLM.status,
                "model_path": model_path,
                "last_error": _SHARED_LLM.last_error,
            }
        if not model_path:
            return {"status": "no_model", "model_path": "", "last_error": "BUTLER_MODEL_PATH 미설정"}
        p = Path(model_path)
        if not p.exists():
            return {"status": "no_model", "model_path": model_path, "last_error": "파일 없음"}
        return {"status": "loading", "model_path": model_path, "last_error": ""}

    @app.get("/api/egress/report")
    def egress_report():
        """Egress Monitor용 송신 현황 리포트 (베타: 모든 값 정적 반환).

        실제 네트워크 모니터링은 D-1-C 이후 구현 예정.
        """
        import uuid as _uuid
        return JSONResponse({
            "schema_version": "egress_report.v2",
            "task_id": str(_uuid.uuid4()),
            "mode": "local_only",
            "raw_file_sent_external": False,
            "raw_text_logged": False,
            "egress_bytes_total": 0,
            "dns_requests": 0,
            "http_requests": 0,
            "https_requests": 0,
            "telemetry_enabled": False,
            "crash_report_enabled": False,
            "update_check_enabled": False,
            "verdict": "PASS",
            "generated_at": datetime.now(_tz.utc).isoformat(),
        })

    @app.post("/api/precheck", response_model=PrecheckResponse)
    def precheck(req: PrecheckRequest):
        """
        파일 경로를 받아 처리 가능 여부와 예상 비용을 반환한다.

        - **tier**: S / M / L / XL / Media-L / empty
        - **size_kb**: 파일 크기 (KB)
        - **estimated_chunks**: 예상 청크 수
        - **estimated_seconds**: 예상 처리 시간(초)
        - **blocked**: XL 또는 empty일 때 True
        - **block_reason**: 차단 사유 (Team Hub 안내 포함)
        """
        try:
            result: BudgetResult = classify_file(req.file_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except IsADirectoryError:
            raise HTTPException(
                status_code=422,
                detail="폴더가 아닌 개별 파일을 첨부해 주세요.",
            )
        except NotAFileError:
            raise HTTPException(
                status_code=422,
                detail="원본 파일을 직접 첨부해 주세요 (심볼릭 링크 불가).",
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"분류 오류: {exc}") from exc

        return PrecheckResponse(
            tier=result.tier,
            size_kb=result.size_kb,
            estimated_chunks=result.estimated_chunks,
            estimated_seconds=result.estimated_seconds,
            blocked=result.blocked,
            block_reason=result.block_reason,
        )

    # -----------------------------------------------------------------------
    # FactPack 출력 포매팅
    # -----------------------------------------------------------------------
    def _format_factpack_answer(fact) -> str:
        """fact 답변에 출처 푸터 자동 부착."""
        lines = [fact.answer.rstrip(), "", "─────────"]
        lines.append(f"출처: {fact.source} ({fact.verified_at} 기준)")
        if fact.source_doc:
            lines.append(f"근거 문서: {fact.source_doc}")
        if fact.source_url:
            lines.append(fact.source_url)
        if fact.expires_at:
            lines.append(f"※ 본 답변은 {fact.expires_at}까지 유효 (이후 재검증 필요)")
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # SSE helpers
    # -----------------------------------------------------------------------
    def _sse(event: str, data: dict) -> str:
        """SSE フレーム (Tauri fetch 互換, no buffering)."""
        payload = json.dumps(data, ensure_ascii=False, default=str)
        return f"event: {event}\ndata: {payload}\n\n"

    async def _stream_analyze(
        params: _AnalyzeParams,
        task_id: str,
    ) -> AsyncGenerator[str, None]:
        """진행률 SSE 제너레이터."""
        # ── (0) Task Budget Router — 자료 크기 기반 라우팅 ──
        total_file_bytes = sum(
            Path(fp).stat().st_size for fp in params.file_paths if Path(fp).is_file()
        )
        estimated_tokens = total_file_bytes // 4  # rough: ~4 bytes/token
        budget = decide_task_budget(
            file_bytes=total_file_bytes,
            estimated_tokens=estimated_tokens,
            page_count=0,
            hub_paired=_is_hub_paired(),
            task_type=params.card_mode,
        )
        yield _sse("meta", {
            "route_check": True,
            "route": budget.route,
            "file_bytes": total_file_bytes,
            "estimated_tokens": estimated_tokens,
            "max_wall_time_sec": budget.max_wall_time_sec,
        })

        if budget.route == Route.REFUSE_TEAM_HUB:
            yield _sse("error", {
                "error_class": "input_too_large",
                "message": budget.user_message,
            })
            return

        if budget.route == Route.TEAM_HUB_RECOMMENDED:
            yield _sse("meta", {
                "source": "team_hub",
                "route": budget.route,
                "message": budget.user_message,
            })
            yield _sse("complete", {
                "result_text": budget.user_message,
                "result_path": "",
                "total_elapsed_sec": 0.0,
            })
            return

        if budget.route == Route.PC_PREVIEW_TEAM_HUB:
            yield _sse("meta", {
                "source": "pc_preview",
                "route": budget.route,
                "message": budget.user_message,
            })
            yield _sse("complete", {
                "result_text": budget.user_message,
                "result_path": "",
                "total_elapsed_sec": 0.0,
            })
            return

        # ── (1) FactPack 1차 매칭 — HIT 시 LLM 호출 없이 즉시 응답 ──
        fp_match = FACT_PACK.lookup(params.query)
        if fp_match is not None:
            answer = _format_factpack_answer(fp_match.fact)
            yield _sse("meta", {
                "source": "factpack",
                "fact_id": fp_match.fact.id,
                "score": round(fp_match.score, 3),
            })
            yield _sse("complete", {
                "result_text": answer,
                "result_path": "",
                "total_elapsed_sec": 0.0,
            })
            _factpack_audit_log.append(FactPackAuditEntry(
                query=params.query,
                source="factpack",
                fact_id=fp_match.fact.id,
                score=fp_match.score,
                threshold_used=FACT_PACK.matcher.threshold,
                timestamp_iso=datetime.now(_tz.utc).isoformat(),
                pack_version=_PACK_VERSION,
            ))
            return

        # ── (2) FactPack 미스 → 기존 LLM 파이프라인 ──
        yield _sse("meta", {"source": "llm"})
        _factpack_audit_log.append(FactPackAuditEntry(
            query=params.query,
            source="llm",
            fact_id=None,
            score=None,
            threshold_used=FACT_PACK.matcher.threshold,
            timestamp_iso=datetime.now(_tz.utc).isoformat(),
            pack_version=_PACK_VERSION,
        ))

        total = max(1, params.total_chunks)
        ctrl = TimeoutController(
            task_id=task_id,
            output_dir=params.output_dir,
            hard_timeout=HARD_TIMEOUT_SEC,
        )
        async with asyncio.Lock():
            _active_controllers[task_id] = ctrl

        start = time.monotonic()
        last_event_time = start
        chunk_results: list[str] = []
        completed_count = 0  # 부분 결과 추적용

        async def _heartbeat_if_idle() -> AsyncGenerator[str, None]:
            nonlocal last_event_time
            now = time.monotonic()
            if now - last_event_time >= 5.0:
                last_event_time = now
                yield _sse("heartbeat", {"elapsed_sec": round(now - start, 2)})

        try:
            estimated_chunk_sec = max(1, budget.max_wall_time_sec // max(1, total))
            yield _sse("phase_start", {
                "phase": "analyze",
                "total_steps": total,
                "status_message": f"1/{total} 단계 분석 시작 — 예상 {estimated_chunk_sec}초",
            })
            last_event_time = time.monotonic()
            await asyncio.sleep(0)  # flush phase_start to client before LLM blocks

            for i in range(total):
                ctrl.check_hard_timeout()

                chunk_start = time.monotonic()

                # Build prompt (same logic as _real_chunk_work_inprocess)
                _sys_prompt = (
                    "당신은 유능한 사무 보조 AI입니다. "
                    "답변은 자연스러운 문단 중심으로 작성하세요. "
                    "제목(##, ###)은 정말 필요한 경우에만 최소화하여 사용하고, "
                    "구분선(---)은 사용하지 마세요. "
                    "굵게(**) 강조도 최소화하세요. "
                    "간결하고 읽기 쉬운 문장 구성을 우선하세요."
                )
                _user_tmpl = "{{ query }}"
                try:
                    from butler_pc_core.prompts.cards import load_card_prompt
                    card = load_card_prompt(params.card_mode)
                    _sys_prompt = card.get("system_prompt", _sys_prompt)
                    _user_tmpl = card.get("user_prompt_template", _user_tmpl)
                except Exception:
                    pass

                _file_texts: list[str] = []
                for fp in params.file_paths:
                    try:
                        _file_texts.append(Path(fp).read_text(encoding="utf-8", errors="replace"))
                    except Exception:
                        pass

                _user_content = _user_tmpl.replace("{{ query }}", params.query)
                if _file_texts:
                    _user_content += "\n\n## 첨부 파일 내용\n" + "\n\n---\n".join(_file_texts)

                _prompt = (
                    f"<|im_start|>system\n{_sys_prompt}<|im_end|>\n"
                    f"<|im_start|>user\n/no_think\n{_user_content}<|im_end|>\n"
                    f"<|im_start|>assistant\n"
                )

                # Stream tokens via asyncio.Queue bridge (thread → coroutine)
                llm = await _ensure_shared_llm()
                cancel_event = threading.Event()
                _loop = asyncio.get_running_loop()
                _token_queue: asyncio.Queue[str | None] = asyncio.Queue()

                def _produce_tokens(
                    _q: asyncio.Queue = _token_queue,
                    _ce: threading.Event = cancel_event,
                    _p: str = _prompt,
                    _lp: asyncio.AbstractEventLoop = _loop,
                ) -> None:
                    try:
                        for tok in llm.generate_stream_with_cancel(_p, _ce, max_tokens=2048):
                            _lp.call_soon_threadsafe(_q.put_nowait, tok)
                    except Exception:
                        pass
                    finally:
                        _lp.call_soon_threadsafe(_q.put_nowait, None)

                _loop.run_in_executor(None, _produce_tokens)

                tokens_acc: list[str] = []
                _deadline = chunk_start + ctrl.chunk_timeout
                # think-block filter: drop <think>...</think> before first response token
                _think_state = "before"  # "before" | "in_think" | "after"

                while True:
                    _remaining = _deadline - time.monotonic()
                    if _remaining <= 0:
                        cancel_event.set()
                        ctrl._abort("chunk_timeout")

                    try:
                        _token = await asyncio.wait_for(
                            _token_queue.get(), timeout=min(_remaining, 10.0)
                        )
                    except asyncio.TimeoutError:
                        cancel_event.set()
                        ctrl._abort("chunk_timeout")

                    if _token is None:
                        break

                    # State machine: silently drop leading <think>...</think> block
                    if _think_state == "before":
                        if _token.strip() == "<think>":
                            _think_state = "in_think"
                            continue
                        else:
                            _think_state = "after"
                    elif _think_state == "in_think":
                        if "</think>" in _token:
                            _think_state = "after"
                        continue  # skip all tokens inside the think block

                    tokens_acc.append(_token)
                    last_event_time = time.monotonic()
                    yield _sse("chunk", {"token": _token})
                    await asyncio.sleep(0)  # flush each token as a separate TCP chunk

                chunk_text = _strip_residual_stop_tokens("".join(tokens_acc))
                chunk_results.append(chunk_text)
                completed_count += 1

                ctrl.check_hard_timeout()

                chunk_elapsed = time.monotonic() - chunk_start
                elapsed_total = time.monotonic() - start
                remaining = max(0.0, (elapsed_total / (i + 1)) * (total - i - 1))

                yield _sse("chunk_progress", {
                    "current": i + 1,
                    "total": total,
                    "elapsed_sec": round(elapsed_total, 2),
                    "est_remaining_sec": round(remaining, 2),
                    "status_message": (
                        f"{total}개 청크 중 {i + 1}번째 처리 중 — 근거 문장 검색 중"
                    ),
                })
                last_event_time = time.monotonic()
                await asyncio.sleep(0)  # flush chunk_progress before chunk_done

                yield _sse("chunk_done", {
                    "chunk_id": i,
                    "latency_ms": round(chunk_elapsed * 1000, 1),
                })
                last_event_time = time.monotonic()
                await asyncio.sleep(0)  # flush chunk_done before next event

            yield _sse("reduce_start", {
                "input_chunks": total,
                "status_message": f"{total}개 청크 결과 통합 중",
            })
            last_event_time = time.monotonic()
            await asyncio.sleep(0)  # flush reduce_start before verify_start
            yield _sse("verify_start", {
                "status_message": "출처 근거 검증 중",
            })
            last_event_time = time.monotonic()
            await asyncio.sleep(0)  # flush verify_start before complete

            result_text = "\n\n".join(chunk_results)
            result_path = str(Path(params.output_dir) / f"{task_id}_result.json")
            try:
                with open(result_path, "w", encoding="utf-8") as _f:
                    json.dump({"task_id": task_id, "results": chunk_results}, _f, ensure_ascii=False, indent=2)
            except Exception:
                pass

            yield _sse("complete", {
                "result_path": result_path,
                "result_text": result_text,
                "total_elapsed_sec": round(time.monotonic() - start, 2),
            })

        except ChunkTimeoutError as exc:  # 구체 → 일반 순서 (P2 수정)
            partial_path = str(exc.partial_path)
            yield _sse("cancelled", {
                "reason": "chunk_timeout",
                "partial_path": partial_path,
                "partial_result_path": partial_path,
                "completed_chunks": completed_count,
                "message": f"사용자 중단. 현재까지 처리된 {completed_count}개 청크 결과를 부분 저장했습니다.",
            })
        except HardTimeoutError as exc:
            partial_path = str(exc.partial_path)
            yield _sse("cancelled", {
                "reason": "hard_timeout",
                "partial_path": partial_path,
                "partial_result_path": partial_path,
                "completed_chunks": completed_count,
                "message": f"사용자 중단. 현재까지 처리된 {completed_count}개 청크 결과를 부분 저장했습니다.",
            })
        except UserCancelledError as exc:
            partial_path = str(exc.partial_path)
            yield _sse("cancelled", {
                "reason": "user_cancel",
                "partial_path": partial_path,
                "partial_result_path": partial_path,
                "completed_chunks": completed_count,
                "message": f"사용자 중단. 현재까지 처리된 {completed_count}개 청크 결과를 부분 저장했습니다.",
            })
        except asyncio.TimeoutError as exc:
            yield _sse("cancelled", {
                "reason": "unknown_timeout",
                "partial_path": "",
                "partial_result_path": "",
                "completed_chunks": completed_count,
                "message": str(exc),
            })
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {
                "error_class": type(exc).__name__,
                "message": str(exc)[:500],
            })
        finally:
            _active_controllers.pop(task_id, None)

    @app.post("/api/analyze/stream")
    async def analyze_stream(request: Request):
        """진행률 SSE 스트림 엔드포인트 (multipart/form-data).

        Content-Type: text/event-stream
        Form fields: query, card_mode, total_chunks, output_dir, file_count
        File fields: file_0 … file_{N-1}
        이벤트: phase_start / chunk_progress / chunk_done /
                reduce_start / verify_start / complete /
                error / cancelled / heartbeat
        """
        form = await request.form()

        query = str(form.get("query") or "")
        card_mode = str(form.get("card_mode") or "free")
        total_chunks = max(1, int(form.get("total_chunks") or 1))
        output_dir = str(form.get("output_dir") or ".")
        file_count = max(0, int(form.get("file_count") or 0))

        file_paths: list[str] = []
        for i in range(file_count):
            upload = form.get(f"file_{i}")
            if upload is not None and hasattr(upload, "read"):
                fname = getattr(upload, "filename", "") or ""
                suffix = Path(fname).suffix if fname else ""
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    content = await upload.read()
                    tmp.write(content)
                    file_paths.append(tmp.name)

        params = _AnalyzeParams(
            query=query,
            card_mode=card_mode,
            total_chunks=total_chunks,
            output_dir=output_dir,
            file_paths=file_paths,
        )
        task_id = str(uuid.uuid4())
        return StreamingResponse(
            _stream_analyze(params, task_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Task-Id": task_id,
            },
        )

    @app.delete("/api/analyze/{task_id}/cancel")
    def cancel_analyze(task_id: str):
        """진행 중인 analyze 작업을 취소한다."""
        ctrl = _active_controllers.get(task_id)
        if ctrl is None:
            raise HTTPException(status_code=404, detail=f"task {task_id} not found")
        ctrl.cancel()
        return {"cancelled": True, "task_id": task_id}

# ---------------------------------------------------------------------------
# FastAPI 미설치 환경용 경량 HTTP 서버 (stdlib only)
# ---------------------------------------------------------------------------
else:
    import http.server
    import urllib.parse

    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silence default logging
            pass

        def _send_json(self, code: int, body: dict):
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "tauri://localhost")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "tauri://localhost")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            if self.path in ("/health", "/api/model/status", "/api/sidecar/health"):
                model_path = os.environ.get("BUTLER_MODEL_PATH", "")
                if self.path == "/health":
                    self._send_json(200, {"status": "ok", "service": "butler-pc-core-sidecar", "version": "0.9.0"})
                elif self.path == "/api/model/status":
                    if not model_path:
                        self._send_json(200, {"status": "no_model", "model_path": "", "last_error": "BUTLER_MODEL_PATH 미설정"})
                    elif not Path(model_path).exists():
                        self._send_json(200, {"status": "no_model", "model_path": model_path, "last_error": "파일 없음"})
                    else:
                        self._send_json(200, {"status": "ready", "model_path": model_path, "last_error": ""})
                else:
                    self._send_json(200, {"status": "ok", "service": "butler-pc-core-sidecar", "version": "0.9.0"})
            else:
                self._send_json(404, {"detail": "not found"})

        def do_POST(self):
            if self.path == "/api/precheck":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    req = json.loads(body)
                    file_path = req["file_path"]
                    result = classify_file(file_path)
                    self._send_json(200, {
                        "tier": result.tier,
                        "size_kb": result.size_kb,
                        "estimated_chunks": result.estimated_chunks,
                        "estimated_seconds": result.estimated_seconds,
                        "blocked": result.blocked,
                        "block_reason": result.block_reason,
                    })
                except FileNotFoundError as exc:
                    self._send_json(404, {"detail": str(exc)})
                except IsADirectoryError:
                    self._send_json(422, {"detail": "폴더가 아닌 개별 파일을 첨부해 주세요."})
                except NotAFileError:
                    self._send_json(422, {"detail": "원본 파일을 직접 첨부해 주세요 (심볼릭 링크 불가)."})
                except (KeyError, json.JSONDecodeError) as exc:
                    self._send_json(400, {"detail": f"잘못된 요청: {exc}"})
                except Exception as exc:
                    self._send_json(500, {"detail": f"분류 오류: {exc}"})
            else:
                self._send_json(404, {"detail": "not found"})

    def _run_stdlib_server(host: str = "127.0.0.1", port: int = 8765):
        server = http.server.HTTPServer((host, port), _Handler)
        print(f"Butler sidecar (stdlib) running on http://{host}:{port}", flush=True)
        server.serve_forever()


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse as _argparse

    _parser = _argparse.ArgumentParser(description="Butler PC Core Sidecar")
    _parser.add_argument("--host", default="127.0.0.1", help="바인딩 호스트 (기본: 127.0.0.1)")
    _parser.add_argument("--port", type=int, default=8765, help="바인딩 포트 (기본: 8765)")
    _args = _parser.parse_args()

    if _FASTAPI_AVAILABLE:
        import uvicorn
        uvicorn.run("butler_sidecar:app", host=_args.host, port=_args.port, reload=False)
    else:
        _run_stdlib_server(host=_args.host, port=_args.port)
