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
)
from butler_pc_core.runtime.timeout_controller import (
    TimeoutController,
    PartialResultError,
    HardTimeoutError,
    ChunkTimeoutError,
    UserCancelledError,
    HARD_TIMEOUT_SEC,
)
from datetime import datetime, timezone as _tz

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
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "butler-pc-core-sidecar", "version": "0.9.0"}

    @app.get("/api/sidecar/health")
    def sidecar_health():
        model_path = os.environ.get("BUTLER_MODEL_PATH", "")
        model_status = "ready" if (model_path and Path(model_path).exists()) else "no_model"
        return {
            "status": "ok",
            "service": "butler-pc-core-sidecar",
            "version": "0.9.0",
            "model_status": model_status,
            "active_tasks": len(_active_controllers),
        }

    @app.get("/api/model/status")
    def model_status():
        model_path = os.environ.get("BUTLER_MODEL_PATH", "")
        if not model_path:
            return {"status": "no_model", "model_path": "", "last_error": "BUTLER_MODEL_PATH 미설정"}
        p = Path(model_path)
        if not p.exists():
            return {"status": "no_model", "model_path": model_path, "last_error": "파일 없음"}
        return {"status": "ready", "model_path": model_path, "last_error": ""}

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

        async def _heartbeat_if_idle() -> AsyncGenerator[str, None]:
            nonlocal last_event_time
            now = time.monotonic()
            if now - last_event_time >= 5.0:
                last_event_time = now
                yield _sse("heartbeat", {"elapsed_sec": round(now - start, 2)})

        try:
            yield _sse("phase_start", {"phase": "analyze", "total_steps": total})
            last_event_time = time.monotonic()

            for i in range(total):
                ctrl.check_hard_timeout()

                chunk_start = time.monotonic()
                async for frame in _heartbeat_if_idle():
                    yield frame

                try:
                    chunk_text: str = await _real_chunk_work_isolated(
                        params, i, ctrl.chunk_timeout
                    )
                    chunk_results.append(chunk_text)
                except asyncio.TimeoutError:
                    ctrl._abort("chunk_timeout")

                ctrl.check_hard_timeout()

                chunk_elapsed = time.monotonic() - chunk_start
                elapsed_total = time.monotonic() - start
                remaining = max(0.0, (elapsed_total / (i + 1)) * (total - i - 1))

                yield _sse("chunk_progress", {
                    "current": i + 1,
                    "total": total,
                    "elapsed_sec": round(elapsed_total, 2),
                    "est_remaining_sec": round(remaining, 2),
                })
                last_event_time = time.monotonic()

                yield _sse("chunk_done", {
                    "chunk_id": i,
                    "latency_ms": round(chunk_elapsed * 1000, 1),
                })
                last_event_time = time.monotonic()

            yield _sse("reduce_start", {"input_chunks": total})
            last_event_time = time.monotonic()
            yield _sse("verify_start", {})
            last_event_time = time.monotonic()

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
            yield _sse("cancelled", {
                "reason": "chunk_timeout",
                "partial_path": str(exc.partial_path),
                "message": str(exc),
            })
        except HardTimeoutError as exc:
            yield _sse("cancelled", {
                "reason": "hard_timeout",
                "partial_path": str(exc.partial_path),
                "message": str(exc),
            })
        except UserCancelledError as exc:
            yield _sse("cancelled", {
                "reason": "user_cancel",
                "partial_path": str(exc.partial_path),
                "message": str(exc),
            })
        except asyncio.TimeoutError as exc:
            yield _sse("cancelled", {
                "reason": "unknown_timeout",
                "partial_path": "",
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
