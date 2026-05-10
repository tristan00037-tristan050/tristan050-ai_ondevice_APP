"""tests/request_parsing/test_parser.py — D-3 카드 1 파서 단위 테스트."""
import pytest
from datetime import date

from butler_pc_core.request_parsing.parser import (
    MIN_TEXT_LENGTH,
    MAX_TEXT_LENGTH,
    ParseError,
    TextTooShortError,
    TextTooLongError,
    ParsedResult,
    mask_pii,
    parse_korean_date,
    validate_schema,
    confidence_level,
    parse_text,
)

# ── 샘플 텍스트 ───────────────────────────────────────────────────────────────
_SAMPLE_MAIL = (
    "안녕하세요. 이번 주 금요일까지 Q1 실적 보고서를 작성해 주시면 감사하겠습니다. "
    "함께 분기 손익계산서 파일도 첨부해 주시기 바랍니다. "
    "검토 후 빠르게 피드백 드리겠습니다."
)

_FORMAL_REQUEST = (
    "대표님께 드립니다. "
    "다음 주 화요일까지 계약서 검토 및 날인을 부탁드립니다. "
    "관련 자료는 별첨을 확인해 주시면 감사하겠습니다. "
    "협조 부탁드립니다."
)


# ── 길이 검증 ─────────────────────────────────────────────────────────────────

def test_too_short_raises():
    with pytest.raises(TextTooShortError):
        parse_text("짧은 텍스트")


def test_too_long_raises():
    with pytest.raises(TextTooLongError):
        parse_text("가" * (MAX_TEXT_LENGTH + 1))


def test_valid_length_parses():
    result = parse_text(_SAMPLE_MAIL)
    assert isinstance(result, ParsedResult)
    assert result.confidence > 0


# ── PII 마스킹 ────────────────────────────────────────────────────────────────

def test_mask_pii_rrn():
    text = "주민번호: 900101-1234567 입니다."
    masked = mask_pii(text)
    assert "900101-1234567" not in masked
    assert "<rrn_masked>" in masked


def test_mask_pii_email():
    text = "연락처: user@example.com 으로 메일 주세요."
    masked = mask_pii(text)
    assert "user@example.com" not in masked
    assert "<email_masked>" in masked


def test_mask_pii_phone():
    text = "010-1234-5678 로 연락 바랍니다."
    masked = mask_pii(text)
    assert "010-1234-5678" not in masked


# ── 한국어 날짜 파싱 ──────────────────────────────────────────────────────────

def test_parse_next_tuesday():
    # 2026-05-08 (금요일) 기준 → 다음 주 화요일 = 2026-05-12
    result = parse_korean_date("다음 주 화요일까지", today=date(2026, 5, 8))
    assert result == "2026-05-12"


def test_parse_this_friday():
    # 2026-05-08 (금요일) 기준 → 이번 주 금요일 = 2026-05-08 (당일)
    result = parse_korean_date("이번 주 금요일", today=date(2026, 5, 8))
    assert result == "2026-05-08"


def test_parse_month_day():
    result = parse_korean_date("5월 20일까지", today=date(2026, 5, 8))
    assert result == "2026-05-20"


def test_parse_eom():
    result = parse_korean_date("이번 달 말까지", today=date(2026, 5, 8))
    assert result == "2026-05-31"


def test_parse_no_date_returns_none():
    result = parse_korean_date("날짜 언급 없는 메시지입니다.")
    assert result is None


# ── JSON Schema 검증 ──────────────────────────────────────────────────────────

def test_validate_schema_valid():
    data = {
        "actions": [{"text": "보고서 작성", "priority": "P1", "rationale": "긴급"}],
        "deadline": {"raw_text": "다음 주 금요일", "parsed_date": "2026-05-15"},
        "required_materials": [{"name": "손익계산서", "is_optional": False}],
        "intent": {"summary": "보고서 요청", "tone": "formal", "expected_response": "회신"},
        "confidence": 0.85,
    }
    errors = validate_schema(data)
    assert errors == []


def test_validate_schema_missing_key():
    data = {
        "actions": [],
        "deadline": {"raw_text": "", "parsed_date": None},
        "required_materials": [],
        # intent 누락
        "confidence": 0.8,
    }
    errors = validate_schema(data)
    assert any("intent" in e or "필수 키" in e for e in errors)


def test_validate_schema_invalid_priority():
    data = {
        "actions": [{"text": "작업", "priority": "X1"}],
        "deadline": {"raw_text": "", "parsed_date": None},
        "required_materials": [],
        "intent": {"summary": "요약", "tone": "formal", "expected_response": ""},
        "confidence": 0.8,
    }
    errors = validate_schema(data)
    assert any("priority" in e for e in errors)


# ── 신뢰도 분기 ───────────────────────────────────────────────────────────────

def test_confidence_level_high():
    assert confidence_level(0.95) == "high"


def test_confidence_level_medium():
    assert confidence_level(0.80) == "medium"


def test_confidence_level_low():
    assert confidence_level(0.60) == "low"


def test_confidence_level_failed():
    assert confidence_level(0.40) == "failed"


# ── 휴리스틱 파싱 결과 ────────────────────────────────────────────────────────

def test_heuristic_extracts_deadline():
    result = parse_text(_SAMPLE_MAIL, today=date(2026, 5, 8))
    assert result.deadline is not None
    # 이번 주 금요일 = 2026-05-08
    assert result.deadline.parsed_date is not None


def test_heuristic_extracts_actions():
    result = parse_text(_FORMAL_REQUEST, today=date(2026, 5, 8))
    assert len(result.actions) >= 1


def test_result_masked_text_set():
    text_with_pii = (
        "user@company.com 으로 답변 부탁드립니다. "
        "이번 주 금요일까지 계약서를 검토해 주세요. "
        "빠른 회신 부탁드립니다. 감사합니다."
    )
    result = parse_text(text_with_pii, today=date(2026, 5, 8))
    assert "user@company.com" not in result.masked_text
    assert "<email_masked>" in result.masked_text


# ── 3차 정정: 텍스트 짤림 + 자료 분리 + 시간 추출 ─────────────────────────────

def test_action_text_not_truncated_on_long_input():
    long_text = (
        "안녕하세요. 이번 달 말일까지 이번 분기 전체 실적 데이터를 기반으로 손익계산서 항목별 "
        "상세 분석 보고서를 작성하고 관련 팀에 배포해 주시기 바랍니다. "
        "빠른 처리 부탁드립니다."
    )
    result = parse_text(long_text, today=date(2026, 5, 8))
    assert len(result.actions) >= 1
    for action in result.actions:
        # 50자 또는 60자 경계에서 정확히 잘린 텍스트가 없어야 함
        assert len(action.text) not in (50, 60) or not action.text[-1].isalpha(), \
            f"Action text suspiciously truncated at {len(action.text)} chars: {action.text!r}"
        assert len(action.text) > 5


def test_action_not_in_required_files():
    # "보고서를 검토해 주시면" — 보고서는 액션 대상, 필요 자료 X
    text = (
        "안녕하세요. 다음 주 화요일까지 이번 분기 실적 보고서를 검토해 주시면 감사하겠습니다. "
        "협조 부탁드립니다."
    )
    result = parse_text(text, today=date(2026, 5, 8))
    mat_names = [m.name for m in result.required_materials]
    action_ctx_mats = [n for n in mat_names if "보고서" in n]
    assert len(action_ctx_mats) == 0, \
        f"액션 문맥의 '보고서'가 필요 자료로 추출됨: {action_ctx_mats}"


def test_required_files_extracts_actual_documents():
    # "파일도 첨부해 주시기 바랍니다" — 실제 자료가 필요 자료로 추출되어야 함
    result = parse_text(_SAMPLE_MAIL, today=date(2026, 5, 8))
    mat_names = [m.name for m in result.required_materials]
    assert any("계산서" in n or "파일" in n for n in mat_names), \
        f"'손익계산서 파일'이 필요 자료에 없음: {mat_names}"


def test_deadline_includes_time():
    text = (
        "다음 주 화요일 오후 3시까지 계약서 검토 및 날인을 부탁드립니다. "
        "빠른 회신 부탁드립니다."
    )
    result = parse_text(text, today=date(2026, 5, 8))
    assert result.deadline.time_text, "time_text가 비어 있음"
    assert "3시" in result.deadline.time_text, \
        f"'3시'가 time_text에 없음: {result.deadline.time_text!r}"
    assert "오후" in result.deadline.time_text, \
        f"'오후'가 time_text에 없음: {result.deadline.time_text!r}"


def test_streaming_last_chunk_received():
    # to_dict()에 time_text 포함 여부 — SSE 스트리밍 complete 이벤트 직렬화 검증
    text = (
        "다음 주 화요일 오후 3시까지 계약서 검토 및 날인을 부탁드립니다. "
        "빠른 회신 부탁드립니다."
    )
    result = parse_text(text, today=date(2026, 5, 8))
    d = result.to_dict()
    assert "time_text" in d["deadline"], "to_dict()에 deadline.time_text 필드 누락"
    assert d["deadline"]["time_text"] == result.deadline.time_text
