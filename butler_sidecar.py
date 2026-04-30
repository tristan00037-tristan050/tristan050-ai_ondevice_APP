"""
butler_sidecar.py
=================
Butler PC Core – 로컬 사이드카 HTTP 서버 (FastAPI)

엔드포인트
----------
GET  /health          서버 상태 확인
POST /api/precheck    파일 등급 사전 체크 (file_path)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 레포 루트를 sys.path에 추가 (직접 실행 시)
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

from butler_pc_core.router.task_budget_router import classify_file, BudgetResult

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

        - **tier**: S / M / L / XL / Media-L
        - **size_kb**: 파일 크기 (KB)
        - **estimated_chunks**: 예상 청크 수
        - **estimated_seconds**: 예상 처리 시간(초)
        - **blocked**: XL일 때 True
        - **block_reason**: 차단 사유 (Team Hub 안내 포함)
        """
        try:
            result: BudgetResult = classify_file(req.file_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
