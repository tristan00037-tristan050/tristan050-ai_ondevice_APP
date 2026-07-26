from __future__ import annotations

import threading
import time

from fastapi import APIRouter, HTTPException, Request, Response

from .errors import AssetError
from .service import get_asset_service

router = APIRouter()
_LOCK = threading.Lock()
_LAST_REQUEST: dict[str, float] = {}
_RATE_LIMIT_SECONDS = 0.25


@router.get("/v1/assets/status")
async def asset_status(request: Request, response: Response) -> dict[str, object]:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=403, detail={"code": "LOCALHOST_ONLY"})
    session = getattr(request.state, "capability_session_digest", None)
    if not isinstance(session, str) or not session:
        raise HTTPException(status_code=401, detail={"code": "CAPABILITY_TOKEN_MISSING"})
    now = time.monotonic()
    with _LOCK:
        previous = _LAST_REQUEST.get(session, 0.0)
        if now - previous < _RATE_LIMIT_SECONDS:
            raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED"})
        _LAST_REQUEST[session] = now
        if len(_LAST_REQUEST) > 1024:
            cutoff = now - 60
            for key in [key for key, value in _LAST_REQUEST.items() if value < cutoff]:
                _LAST_REQUEST.pop(key, None)
    response.headers["Cache-Control"] = "no-store"
    try:
        return get_asset_service().get_cached_status()
    except AssetError:
        return {"schema_version": 1, "overall_state": "UNAVAILABLE", "groups": []}
