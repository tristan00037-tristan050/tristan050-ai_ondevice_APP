"""test_download_stability.py — 다운로드 안정성: 다중 호출 동일 결과 + TTL 만료 404."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

try:
    from fastapi.testclient import TestClient
    import pandas as pd
    import openpyxl
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

_skip = pytest.mark.skipif(not _DEPS_OK, reason="fastapi/pandas/openpyxl 미설치")


def _make_app():
    """butler_sidecar FastAPI app 직접 생성 (재사용)."""
    import importlib, sys
    # butler_sidecar 모듈을 재임포트하지 않고 app 재사용
    import butler_sidecar  # noqa: F401 — side-effect: registers routes
    from butler_sidecar import app as _app
    return _app


@_skip
def test_same_result_id_multiple_downloads_return_identical_content():
    """동일 result_id를 여러 번 다운로드해도 항상 동일한 xlsx 바이너리를 반환해야 한다."""
    from butler_sidecar import app

    client = TestClient(app)

    # Minimal CSV file to classify
    csv_content = b"\xec\xa0\x81\xec\x9a\x94,\xea\xb1\xb0\xeb\x9e\x98\xec\xb2\x98,\xea\xb8\x88\xec\x95\xa1\n\xea\xb8\x89\xec\x97\xac \xec\xa7\x80\xea\xb8\x89,,1000000\n"
    # Use UTF-8 CSV
    csv_content = "적요,거래처,금액\n급여 지급,,1000000\n통신비 납부,KT,88000\n".encode("utf-8")

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(csv_content)
        csv_path = f.name

    try:
        # 1. Classify
        with open(csv_path, "rb") as fp:
            resp = client.post(
                "/accounting/classify",
                files={"file": ("test.csv", fp, "text/csv")},
                headers={"Accept": "text/event-stream"},
            )
        assert resp.status_code == 200

        # Parse result_id from SSE
        result_id = None
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                import json
                d = json.loads(line[5:])
                if "result_id" in d:
                    result_id = d["result_id"]
        assert result_id is not None, "SSE complete 이벤트에서 result_id를 찾을 수 없음"

        # 2. Download multiple times — all should return identical content
        r1 = client.get(f"/accounting/result/{result_id}/xlsx")
        assert r1.status_code == 200, f"1차 다운로드 실패: {r1.status_code}"

        r2 = client.get(f"/accounting/result/{result_id}/xlsx")
        assert r2.status_code == 200, f"2차 다운로드 실패: {r2.status_code}"

        r3 = client.get(f"/accounting/result/{result_id}/xlsx")
        assert r3.status_code == 200, f"3차 다운로드 실패: {r3.status_code}"

        assert r1.content == r2.content == r3.content, (
            "다중 다운로드 시 바이너리 내용이 달라짐 — 동일해야 함"
        )
    finally:
        Path(csv_path).unlink(missing_ok=True)


@_skip
def test_unknown_result_id_returns_404():
    """존재하지 않는 result_id 조회 시 404를 반환해야 한다."""
    from butler_sidecar import app

    client = TestClient(app)
    resp = client.get("/accounting/result/nonexistent-uuid-99999999/xlsx")
    assert resp.status_code == 404, f"404가 아닌 {resp.status_code} 반환됨"
    assert "result_id" in resp.json().get("detail", "") or "존재" in resp.json().get("detail", ""), (
        f"404 응답에 명확한 오류 메시지 없음: {resp.json()}"
    )


@_skip
def test_result_ttl_constant_is_six_hours():
    """ACCOUNTING_RESULT_TTL이 6시간(21600초)으로 설정되어야 한다."""
    import butler_sidecar as _mod
    # TTL은 모듈 내부 클로저 변수; 소스 확인
    source = Path(_mod.__file__).read_text(encoding="utf-8")
    assert "ACCOUNTING_RESULT_TTL = 21600" in source, (
        "ACCOUNTING_RESULT_TTL이 21600(6시간)이 아님 — 베타 사용자 여유 확보 필요"
    )
