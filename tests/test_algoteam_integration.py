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


# ---------------------------------------------------------------------------
# 단계 8.4 — PR #700 코드 리뷰 결함 정정 검증 (+5 tests)
# ---------------------------------------------------------------------------

@_skip
def test_parse_stream_then_download_md_no_500():
    """P1 #1 회귀 방지: parse_stream 저장 → .md 다운로드 시 500 없음."""
    client = _get_client()
    resp = client.post(
        "/request_parsing/parse_stream",
        json={"text": _SAMPLE_TEXT, "input_format": "text"},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    complete = next((e for e in events if e.get("event") == "complete"), None)
    assert complete is not None
    rid = complete["data"]["result_id"]

    md_resp = client.get(f"/request_parsing/result/{rid}/markdown")
    assert md_resp.status_code == 200, (
        f"다운로드 .md HTTP {md_resp.status_code}: {md_resp.text[:200]}"
    )
    assert len(md_resp.content) > 0, "빈 markdown 응답"


@_skip
def test_parse_stream_then_download_docx_no_500():
    """P1 #1 회귀 방지: parse_stream 저장 → .docx 다운로드 시 500 없음."""
    client = _get_client()
    resp = client.post(
        "/request_parsing/parse_stream",
        json={"text": _SAMPLE_TEXT, "input_format": "text"},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    complete = next((e for e in events if e.get("event") == "complete"), None)
    assert complete is not None
    rid = complete["data"]["result_id"]

    docx_resp = client.get(f"/request_parsing/result/{rid}/docx")
    assert docx_resp.status_code == 200, (
        f"다운로드 .docx HTTP {docx_resp.status_code}: {docx_resp.text[:200]}"
    )
    assert len(docx_resp.content) > 100, "비정상적으로 짧은 docx 응답"


@_skip
def test_parse_file_stream_returns_card1_format():
    """P1 #2 회귀 방지: parse_file_stream도 Card1Extraction 형식 반환 (intent_type/confidence_band)."""
    client = _get_client()
    txt_bytes = _SAMPLE_TEXT.encode("utf-8")
    resp = client.post(
        "/request_parsing/parse_file_stream",
        files={"file": ("sample.txt", io.BytesIO(txt_bytes), "text/plain")},
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    events = _parse_sse_events(resp.text)
    complete = next((e for e in events if e.get("event") == "complete"), None)
    assert complete is not None, "complete 이벤트 없음"
    result = complete["data"].get("result", {})
    # Card1Extraction 영역 필드 확인
    assert "intent_type" in result, f"intent_type 키 없음 — keys: {list(result.keys())}"
    assert "confidence_band" in result, "confidence_band 키 없음"
    assert "actions" in result, "actions 키 없음"
    # actions의 영역 — Card1 형식은 action_text (legacy text 영역 X)
    if result["actions"]:
        a0 = result["actions"][0]
        assert "action_text" in a0, f"action_text 키 없음 (legacy 형식 잔존). keys: {list(a0.keys())}"
    # materials는 list[str] (Card1 형식)
    assert isinstance(result.get("materials", []), list)


@_skip
def test_parse_file_stream_then_download_no_500():
    """P1 #1+#2 회귀 방지: parse_file_stream 저장 → 다운로드 호환 확인."""
    client = _get_client()
    txt_bytes = _SAMPLE_TEXT.encode("utf-8")
    resp = client.post(
        "/request_parsing/parse_file_stream",
        files={"file": ("sample.txt", io.BytesIO(txt_bytes), "text/plain")},
    )
    assert resp.status_code == 200
    events = _parse_sse_events(resp.text)
    complete = next((e for e in events if e.get("event") == "complete"), None)
    assert complete is not None
    rid = complete["data"]["result_id"]

    md_resp = client.get(f"/request_parsing/result/{rid}/markdown")
    assert md_resp.status_code == 200, f"다운로드 .md HTTP {md_resp.status_code}: {md_resp.text[:200]}"
    docx_resp = client.get(f"/request_parsing/result/{rid}/docx")
    assert docx_resp.status_code == 200, f"다운로드 .docx HTTP {docx_resp.status_code}: {docx_resp.text[:200]}"


def test_extract_card1_concurrent_calls_no_env_leak():
    """P2 회귀 방지: extract_card1(skip_llm=True) 동시 호출이 글로벌 SKIP_LLM env에 영향 X.

    이전 영역: butler_sidecar._run_card1_extraction이 os.environ['SKIP_LLM'] 글로벌 mutation →
              동시 요청 시 race condition으로 env 영구화.
    정정: extract_card1(skip_llm=True) 인자로 LLM bypass — env mutation X.
    """
    import os as _os
    from butler_pc_core.card1_extraction import extract_card1

    # 사전 영역 — env에 SKIP_LLM 없음
    _os.environ.pop("SKIP_LLM", None)
    assert _os.environ.get("SKIP_LLM") is None

    # 연속 호출 5회
    for _ in range(5):
        result = extract_card1("내일까지 계약서 보내주세요. 검토 부탁드립니다.", skip_llm=True)
        assert result.intent_type.value in (
            "request", "report", "question", "command", "schedule", "no_action", "unknown"
        )
        # ★ 핵심 검증: env에 SKIP_LLM이 영구 mutation 영역 X
        assert _os.environ.get("SKIP_LLM") is None, (
            "extract_card1(skip_llm=True) 호출 후 os.environ['SKIP_LLM']이 누수됨"
        )
