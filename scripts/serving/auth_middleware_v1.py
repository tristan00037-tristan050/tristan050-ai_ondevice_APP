from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .server_config_v1 import ServerConfig


logger = logging.getLogger('butler.server')


def _safe_status_detail(detail: object) -> object:
    if isinstance(detail, (dict, list, str, int, float, bool)) or detail is None:
        return detail
    return str(detail)


class ButlerAuthMiddleware(BaseHTTPMiddleware):
    """Security + observability middleware.

    Important invariant: never log message content or generated content.
    """

    def __init__(self, app, config: ServerConfig):
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next) -> Response:
        req_id = uuid.uuid4().hex[:12]
        request.state.request_id = req_id
        start = time.perf_counter()
        response: Optional[Response] = None
        status_code = 500

        try:
            self._check_body_size(request)
            self._check_auth(request)
            self._check_allowlist(request)
            response = await call_next(request)
            status_code = response.status_code
        except HTTPException as exc:
            status_code = exc.status_code
            response = JSONResponse(status_code=exc.status_code, content={'detail': _safe_status_detail(exc.detail)})
        except Exception:
            logger.exception('Unhandled request error', extra={'request_id': req_id, 'route': str(request.url.path)})
            status_code = 500
            response = JSONResponse(status_code=500, content={'detail': 'internal_server_error'})

        latency_ms = int((time.perf_counter() - start) * 1000)
        if self.config.log_requests:
            logger.info(json.dumps({
                'request_id': req_id,
                'route': str(request.url.path),
                'method': request.method,
                'status': status_code,
                'latency_ms': latency_ms,
            }, ensure_ascii=False))

        response.headers['X-Request-Id'] = req_id
        response.headers['X-Latency-Ms'] = str(latency_ms)
        response.headers.setdefault('Cache-Control', 'no-store')
        return response

    def _check_body_size(self, request: Request) -> None:
        raw = request.headers.get('content-length', '0')
        try:
            content_length = int(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail='invalid_content_length') from exc
        if content_length > self.config.max_request_body_bytes:
            raise HTTPException(status_code=413, detail='request_body_too_large')

    def _check_auth(self, request: Request) -> None:
        if request.url.path in self.config.open_paths:
            return
        if not self.config.api_key_required:
            return
        auth_header = request.headers.get('authorization', '')
        if not auth_header.startswith('Bearer '):
            raise HTTPException(status_code=401, detail='authentication_required')
        token = auth_header.split(' ', 1)[1].strip()
        if not token or token not in self.config.valid_api_keys:
            raise HTTPException(status_code=403, detail='invalid_api_key')

    def _check_allowlist(self, request: Request) -> None:
        allowed_hosts = self.config.allowed_hosts
        if allowed_hosts == ['*']:
            return
        client_host = request.client.host if request.client else None
        if client_host not in allowed_hosts:
            raise HTTPException(status_code=403, detail='ip_not_allowed')
