"""test_algoteam_integration.py — 단계 8: 카드 1 + 카드 2 PC Core 통합 검증 (4 tests).

검증 항목:
  1. test_card2_api_uses_semantic_mapping     — transform_stream 결과에 slot_results 포함 확인
  2. test_card1_api_uses_card1_extraction    — parse_stream 결과에 intent_type 포함 확인
  3. test_card2_returns_confidence           — slot_results[*].confidence 값이 0~1 범위
  4. test_card1_returns_needs_review_flag    — parse_stream 결과에 needs_review bool 포함
"""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

try:
    from fastapi.testclient import TestClient
    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False

_skip = pytest.mark.skipif(not _FASTAPI_OK, reason="fastapi 미설치")


# ---------------------------------------------------------------------------
# 공용 helpers
# ---------------------------------------------------------------------------

def _parse_sse_events(raw: str) -> list[dict]:
    events = []
    current: dict = {}
    for line in raw.splitlines():
        if line.startswith("event:"):
            current["event"] = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            try:
                current["data"] = json.loads(line.split(":", 1)[1].strip())
            except json.JSONDecodeError:
                current["data"] = {}
        elif line == "" and current:
            events.append(current.copy())
            current = {}
    if current:
        events.append(current)
    return events


def _get_client():
    import butler_sidecar as sidecar
    from butler_pc_core.inference.llm_runtime import LlmRuntime
    sidecar._SHARED_LLM = LlmRuntime(model_path=None)
    return TestClient(sidecar.app)


_SAMPLE_TEXT = (
    "안녕하세요. 내일까지 계약서 파일을 보내주시면 감사하겠습니다. "
    "검토 후 회신드리겠습니다."
)

_SAMPLE_EXTERNAL_MD = (
    "# 사업 개요\n"
    "AI 기반 온디바이스 플랫폼 개발 프로젝트입니다.\n\n"
    "## 사업 영역\n온디바이스 AI 추론 엔진 개발\n\n"
    "## 사업 기간\n2026년 01월 ~ 2026년 12월 (12개월)\n\n"
    "## 예산 영역\n총 사업비 5억원\n\n"
    "## 일정\n착수: 2026-01-01, 완료: 2026-12-31\n"
).encode("utf-8")

_SAMPLE_TEMPLATE_MD = (
    "# 사업 개요\n\n"
    "## 사업 영역\n\n"
    "## 사업 기간\n\n"
    "## 예산 영역\n\n"
    "## 일정\n"
).encode("utf-8")


# ---------------------------------------------------------------------------
# 1. test_card2_api_uses_semantic_mapping
# ---------------------------------------------------------------------------

@_skip
def test_card2_api_uses_semantic_mapping():
    """document_transform/transform_stream complete 이벤트에 slot_results 포함 확인."""
    client = _get_client()
    resp = client.post(
        "/document_transform/transform_stream",
        files={
            "external_file": ("external.md", io.BytesIO(_SAMPLE_EXTERNAL_MD), "text/markdown"),
            "template_file": ("template.md", io.BytesIO(_SAMPLE_TEMPLATE_MD), "text/markdown"),
        },
        data={"include_source_note": "false"},
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    events = _parse_sse_events(resp.text)
    complete = next((e for e in events if e.get("event") == "complete"), None)
    assert complete is not None, "complete 이벤트 없음"
    summary = complete["data"].get("summary", {})
    assert "slot_results" in summary, (
        f"slot_results 키 없음. summary keys: {list(summary.keys())}"
    )


# ---------------------------------------------------------------------------
# 2. test_card1_api_uses_card1_extraction
# ---------------------------------------------------------------------------

@_skip
def test_card1_api_uses_card1_extraction():
    """request_parsing/parse_stream complete 결과에 intent_type 포함 확인 (card1_extraction 통합)."""
    client = _get_client()
    with patch.dict(os.environ, {"SKIP_LLM": "true"}):
        resp = client.post(
            "/request_parsing/parse_stream",
            json={"text": _SAMPLE_TEXT, "input_format": "text"},
        )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    events = _parse_sse_events(resp.text)
    complete = next((e for e in events if e.get("event") == "complete"), None)
    assert complete is not None, "complete 이벤트 없음"
    result = complete["data"].get("result", {})
    assert "intent_type" in result, (
        f"intent_type 키 없음 (card1_extraction 미통합). result keys: {list(result.keys())}"
    )
    assert result["intent_type"] in (
        "request", "report", "question", "command", "schedule", "no_action", "unknown"
    ), f"유효하지 않은 intent_type: {result['intent_type']}"


# ---------------------------------------------------------------------------
# 3. test_card2_returns_confidence
# ---------------------------------------------------------------------------

@_skip
def test_card2_returns_confidence():
    """slot_results[*].confidence 값이 0.0~1.0 범위인지 확인."""
    client = _get_client()
    resp = client.post(
        "/document_transform/transform_stream",
        files={
            "external_file": ("external.md", io.BytesIO(_SAMPLE_EXTERNAL_MD), "text/markdown"),
            "template_file": ("template.md", io.BytesIO(_SAMPLE_TEMPLATE_MD), "text/markdown"),
        },
        data={"include_source_note": "false"},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    complete = next((e for e in events if e.get("event") == "complete"), None)
    assert complete is not None
    slot_results = complete["data"].get("summary", {}).get("slot_results", [])
    assert len(slot_results) > 0, "slot_results가 비어 있음"
    for sr in slot_results:
        conf = sr.get("confidence", -1)
        assert 0.0 <= conf <= 1.0, (
            f"slot={sr.get('slot_id')} confidence={conf} 범위 초과"
        )
        assert "needs_review" in sr, f"slot={sr.get('slot_id')} needs_review 키 없음"


# ---------------------------------------------------------------------------
# 4. test_card1_returns_needs_review_flag
# ---------------------------------------------------------------------------

@_skip
def test_card1_returns_needs_review_flag():
    """request_parsing/parse_stream 결과에 needs_review bool + confidence_band 포함 확인."""
    client = _get_client()
    with patch.dict(os.environ, {"SKIP_LLM": "true"}):
        resp = client.post(
            "/request_parsing/parse_stream",
            json={"text": _SAMPLE_TEXT, "input_format": "text"},
        )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    complete = next((e for e in events if e.get("event") == "complete"), None)
    assert complete is not None
    result = complete["data"].get("result", {})
    # needs_review 필드 확인
    assert "needs_review" in result, (
        f"needs_review 키 없음. result keys: {list(result.keys())}"
    )
    assert isinstance(result["needs_review"], bool), (
        f"needs_review 타입 오류: {type(result['needs_review'])}"
    )
    # confidence_band §6-6 확인
    assert "confidence_band" in result, "confidence_band 키 없음"
    assert result["confidence_band"] in ("auto", "badge", "confirm", "blocked"), (
        f"유효하지 않은 confidence_band: {result['confidence_band']}"
    )
