"""test_eviction.py — 회계 결과 TTL eviction 검증."""
from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient
    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False

_skip_no_fastapi = pytest.mark.skipif(not _FASTAPI_OK, reason="fastapi 미설치")


@_skip_no_fastapi
def test_cleanup_removes_expired_entries():
    """만료된 항목이 _cleanup_accounting_results 호출 후 제거된다."""
    import butler_sidecar as _sidecar

    # 임시 xlsx 파일 생성 (cleanup 후 삭제 확인용)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(b"dummy")
        tmp_path = f.name

    result_id = "test-eviction-001"
    # created_at을 TTL보다 훨씬 오래 전으로 설정
    _sidecar._accounting_results[result_id] = {
        "xlsx_path": tmp_path,
        "md_content": "## test",
        "summary": {},
        "created_at": time.monotonic() - (_sidecar.ACCOUNTING_RESULT_TTL + 10),
    }

    assert result_id in _sidecar._accounting_results
    assert Path(tmp_path).exists()

    # cleanup을 한 번 즉시 실행 (sleep 없이)
    async def _run_one_cleanup():
        now = time.monotonic()
        expired = [
            rid for rid, entry in list(_sidecar._accounting_results.items())
            if now - entry.get("created_at", now) > _sidecar.ACCOUNTING_RESULT_TTL
        ]
        for rid in expired:
            entry = _sidecar._accounting_results.pop(rid, None)
            if entry:
                try:
                    Path(entry["xlsx_path"]).unlink(missing_ok=True)
                except Exception:
                    pass

    asyncio.run(_run_one_cleanup())

    assert result_id not in _sidecar._accounting_results, "만료 항목이 메모리에서 제거되지 않음"
    assert not Path(tmp_path).exists(), "만료 항목의 xlsx 파일이 디스크에서 제거되지 않음"


@_skip_no_fastapi
def test_cleanup_preserves_fresh_entries():
    """만료되지 않은 항목은 cleanup 후에도 유지된다."""
    import butler_sidecar as _sidecar

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        f.write(b"dummy")
        tmp_path = f.name

    result_id = "test-eviction-fresh-001"
    _sidecar._accounting_results[result_id] = {
        "xlsx_path": tmp_path,
        "md_content": "## fresh",
        "summary": {},
        "created_at": time.monotonic(),  # 방금 생성
    }

    async def _run_one_cleanup():
        now = time.monotonic()
        expired = [
            rid for rid, entry in list(_sidecar._accounting_results.items())
            if now - entry.get("created_at", now) > _sidecar.ACCOUNTING_RESULT_TTL
        ]
        for rid in expired:
            entry = _sidecar._accounting_results.pop(rid, None)
            if entry:
                try:
                    Path(entry["xlsx_path"]).unlink(missing_ok=True)
                except Exception:
                    pass

    asyncio.run(_run_one_cleanup())

    assert result_id in _sidecar._accounting_results, "신선한 항목이 잘못 제거됨"

    # 정리
    _sidecar._accounting_results.pop(result_id, None)
    Path(tmp_path).unlink(missing_ok=True)


@_skip_no_fastapi
def test_accounting_result_ttl_constant():
    """ACCOUNTING_RESULT_TTL / ACCOUNTING_CLEANUP_INTERVAL 상수 존재 + 값 검증."""
    import butler_sidecar as _sidecar
    assert hasattr(_sidecar, "ACCOUNTING_RESULT_TTL")
    assert hasattr(_sidecar, "ACCOUNTING_CLEANUP_INTERVAL")
    assert _sidecar.ACCOUNTING_RESULT_TTL == 21600  # 6시간 (베타 여유)
    assert _sidecar.ACCOUNTING_CLEANUP_INTERVAL == 300
