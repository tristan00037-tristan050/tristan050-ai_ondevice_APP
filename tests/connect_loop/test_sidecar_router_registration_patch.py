"""maindev v1.2 이식 — router_decide 등록 검증 (코덱스 구현 기준 조정).

maindev 는 patches/0001-*.patch 파일을 검사했으나, 코덱스 구현은 butler_sidecar.py 에
직접 include_router 로 등록(별도 패치 파일 없음) → 실제 등록 소스를 직접 검증하도록 조정.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.routing_introspection import collect_app_paths


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_butler_sidecar_registers_router_decide_without_new_app():
    text = (_repo_root() / "butler_sidecar.py").read_text(encoding="utf-8")
    # Fixture drift: the import was reformatted to a parenthesized multi-line
    # form; match it whitespace/newline-insensitively (intent: router_decide is
    # imported into butler_sidecar.py, not via a new FastAPI app).
    assert re.search(
        r"from\s+butler_pc_core\.sidecar\.routes\.router_decide\s+import\s*\(?\s*"
        r"router\s+as\s+router_decide_router",
        text,
    ), "router_decide router must be imported into butler_sidecar.py"
    assert "app.include_router(router_decide_router)" in text


def test_router_decide_module_defines_router_not_new_app():
    """router_decide.py 는 APIRouter 만 정의하고 새 FastAPI() 앱을 만들지 않는다."""
    text = (_repo_root() / "butler_pc_core" / "sidecar" / "routes" / "router_decide.py").read_text(encoding="utf-8")
    assert "APIRouter()" in text
    assert not re.search(r"FastAPI\s*\(", text), "router_decide 는 새 FastAPI 앱을 만들면 안 됨"


def test_router_decide_registered_in_live_app():
    """실제 sidecar app 에 /v1/router/decide 라우트가 등록되어 있다(가능 시)."""
    import importlib

    butler_sidecar = importlib.import_module("butler_sidecar")
    if not getattr(butler_sidecar, "_FASTAPI_AVAILABLE", False):
        import pytest

        pytest.skip("FastAPI 미가용")
    paths = collect_app_paths(butler_sidecar.app)
    assert "/v1/router/decide" in paths
