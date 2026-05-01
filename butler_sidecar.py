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

# task_id → TimeoutController マップ (キャンセル用)
_active_controllers: dict[str, TimeoutController] = {}
_controllers_lock = asyncio.Lock() if _FASTAPI_AVAILABLE else None  # type: ignore[assignment]


def _stub_chunk_work(chunk_index: int) -> None:
    """청크 처리 스텁 — Phase 4에서 실제 파이프라인 연결 예정."""

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
if _FASTAPI_AVAILABLE:
    app = FastAPI(
        title="Butler PC Core Sidecar",
        version="0.9.0",
        description="Butler PC Core 로컬 사이드카 — 파일 사전 체크 및 작업 라우팅",
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
                ctrl.check_hard_timeout()  # 빠른 하드 타임아웃 검사 (타임아웃 없이)

                chunk_start = time.monotonic()
                async for frame in _heartbeat_if_idle():
                    yield frame

                # 실제 청크 처리 함수를 chunk_timeout 안에 강제 종료 (P1 수정)
                loop = asyncio.get_event_loop()
                try:
                    await asyncio.wait_for(
                        loop.run_in_executor(None, _stub_chunk_work, i),
                        timeout=ctrl.chunk_timeout,
                    )
                except asyncio.TimeoutError:
                    ctrl._abort("chunk_timeout")  # ChunkTimeoutError 발생

                ctrl.check_hard_timeout()  # 청크 완료 후 하드 타임아웃 재확인

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

            result_path = str(Path(params.output_dir) / f"{task_id}_result.json")
            yield _sse("complete", {
                "result_path": result_path,
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
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
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
    if _FASTAPI_AVAILABLE:
        import uvicorn
        uvicorn.run("butler_sidecar:app", host="127.0.0.1", port=8765, reload=False)
    else:
        _run_stdlib_server()
