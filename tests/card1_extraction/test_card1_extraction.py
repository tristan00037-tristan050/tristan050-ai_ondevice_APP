"""test_card1_extraction.py — 단계 5+6.4: card1_extraction 모듈 검증 (27 tests)."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from butler_pc_core.card1_extraction import (
    Card1Extraction,
    IntentType,
    SentenceType,
    extract_card1,
)
from butler_pc_core.card1_extraction.confidence import (
    ConfidenceFactors,
    compute_card1_confidence,
)
from butler_pc_core.card1_extraction.contracts import ExtractedAction
from butler_pc_core.card1_extraction.llm_extractor import extract_with_llm
from butler_pc_core.card1_extraction.parser import (
    classify_sentence_type,
    extract_actions_candidates,
    extract_deadlines,
    extract_materials,
)
from butler_pc_core.card1_extraction.verifier import verify_card1_extraction


# ── 1~4: DEADLINE_PATTERNS ────────────────────────────────────────────────────

def test_deadline_today():
    text = "오늘 중에 자료를 제출해주시기 바랍니다."
    found = extract_deadlines(text)
    assert any("오늘" in d for d in found), f"마감 미감지: {found}"


def test_deadline_tomorrow():
    text = "내일까지 검토 의견 회신 부탁드립니다."
    found = extract_deadlines(text)
    assert any("내일" in d for d in found), f"마감 미감지: {found}"


def test_deadline_specific_date():
    text = "5월 20일까지 계약서를 제출해주세요."
    found = extract_deadlines(text)
    assert any("일까지" in d or "월" in d for d in found), f"마감 미감지: {found}"


def test_deadline_time_expression():
    text = "오전 10시까지 보고서를 올려주세요."
    found = extract_deadlines(text)
    assert any("시까지" in d for d in found), f"시간 마감 미감지: {found}"


# ── 5: ACTION_VERBS ───────────────────────────────────────────────────────────

def test_action_verbs_detected():
    text = "계약서 파일을 내일까지 보내주시면 감사하겠습니다. 검토 후 회신드리겠습니다."
    candidates = extract_actions_candidates(text)
    assert len(candidates) >= 1, "ACTION_VERBS 포함 문장 미감지"
    assert any("보내" in c or "회신" in c for c in candidates)


# ── 6: MATERIAL_WORDS ─────────────────────────────────────────────────────────

def test_material_words_detected():
    text = "견적서와 계약서 파일을 첨부해주세요. 회의록도 함께 보내주시기 바랍니다."
    found = extract_materials(text)
    assert "견적서" in found or "계약서" in found or "파일" in found
    assert "회의록" in found


# ── 7~14: 문형 8유형 ──────────────────────────────────────────────────────────

def test_sentence_type_interrogative():
    text = "이 보고서를 누가 작성했나요?"
    assert classify_sentence_type(text) == SentenceType.INTERROGATIVE


def test_sentence_type_declarative():
    text = "이번 프로젝트의 예산 규모는 5천만원입니다."
    assert classify_sentence_type(text) == SentenceType.DECLARATIVE


def test_sentence_type_imperative():
    text = "계약서를 지금 바로 보내주세요."
    assert classify_sentence_type(text) == SentenceType.IMPERATIVE


def test_sentence_type_propositive():
    text = "이 문제를 팀원들과 같이 검토해봅시다."
    assert classify_sentence_type(text) == SentenceType.PROPOSITIVE


def test_sentence_type_reportive():
    text = "이번 회의 결과를 보고드립니다."
    assert classify_sentence_type(text) == SentenceType.REPORTIVE


def test_sentence_type_conditional():
    text = "예산이 확정된다면 즉시 착수하겠습니다."
    assert classify_sentence_type(text) == SentenceType.CONDITIONAL


def test_sentence_type_negative():
    text = "해당 작업은 아직 완료되지 않았습니다."
    assert classify_sentence_type(text) == SentenceType.NEGATIVE


def test_sentence_type_complex():
    text = "내일까지 보고서를 검토하실 수 있나요? 문의사항은 연락주시기 바랍니다."
    assert classify_sentence_type(text) == SentenceType.COMPLEX


# ── 15: confidence evidence 기반 ──────────────────────────────────────────────

def test_confidence_evidence_based():
    factors = ConfidenceFactors(
        action_verb_count=3,
        deadline_found=True,
        deadline_claimed=True,
        material_count=2,
        action_count=2,
        hallucination_count=0,
    )
    conf = compute_card1_confidence(factors)
    # Platt 보정 후: base(0.35)+intent(0.20)+deadline(0.20)+material(0.10)+action(0.10)=0.95
    # calibrated = 0.85 * 0.95 + 0.05 ≈ 0.858
    assert conf >= 0.85, f"evidence 충분할 때 신뢰도 0.85+ 기대, 실제: {conf}"


# ── 16: hallucination penalty ─────────────────────────────────────────────────

def test_confidence_hallucination_penalty():
    base_factors = ConfidenceFactors(
        action_verb_count=2,
        deadline_found=True,
        deadline_claimed=True,
        material_count=1,
        action_count=1,
        hallucination_count=0,
    )
    penalized_factors = ConfidenceFactors(
        action_verb_count=2,
        deadline_found=True,
        deadline_claimed=True,
        material_count=1,
        action_count=1,
        hallucination_count=2,
    )
    base_conf     = compute_card1_confidence(base_factors)
    penalized_conf = compute_card1_confidence(penalized_factors)
    assert penalized_conf < base_conf, (
        f"hallucination penalty 미적용: base={base_conf:.3f}, penalized={penalized_conf:.3f}"
    )
    assert base_conf - penalized_conf >= 0.20, (
        f"penalty 2건(-0.30 → Platt 보정 후 ~0.255)이 반영되어야 합니다: diff={base_conf - penalized_conf:.3f}"
    )


# ── 17: verifier — 원문 없는 마감일 차단 ─────────────────────────────────────

def test_verifier_blocks_no_evidence_deadline():
    source = "파일 좀 보내주세요."
    extraction = Card1Extraction(
        intent="파일 전달 요청",
        intent_type=IntentType.REQUEST,
        deadline=None,
        deadline_raw="다음 달 초",      # 원문에 없는 마감 주장
        materials=["파일"],
        actions=[],
        sentence_type=SentenceType.IMPERATIVE,
        confidence=0.70,
        needs_review=False,
        reason_code="",
    )
    verified, h_count = verify_card1_extraction(extraction, source)
    assert verified.deadline_raw == "", "원문 없는 마감일이 제거되어야 합니다"
    assert verified.deadline is None
    assert h_count >= 1


# ── 18: verifier — 부정형 문장 액션 차단 ─────────────────────────────────────

def test_verifier_blocks_negative_action():
    source = "해당 작업은 현재 진행되지 않았습니다."
    action = ExtractedAction(
        action_text="작업 진행",
        source_evidence="해당 작업은 현재 진행되지 않았습니다.",
        confidence=0.60,
    )
    extraction = Card1Extraction(
        intent="작업 진행 요청",
        intent_type=IntentType.REQUEST,
        deadline=None,
        deadline_raw="",
        materials=[],
        actions=[action],
        sentence_type=SentenceType.NEGATIVE,
        confidence=0.60,
        needs_review=True,
        reason_code="",
    )
    verified, h_count = verify_card1_extraction(extraction, source)
    assert len(verified.actions) == 0, "부정형 문장의 액션은 모두 제거되어야 합니다"
    assert h_count >= 1


# ── 19: LLM extractor — mock structured output ───────────────────────────────

def test_llm_extractor_structured_output():
    mock_json = (
        '{"intent": "계약서 검토 요청", "intent_type": "request",'
        ' "deadline": "2026-05-12", "deadline_raw": "내일까지",'
        ' "materials": ["계약서"],'
        ' "actions": [{"action_text": "계약서 검토", "source_evidence":'
        ' "내일까지 계약서를 검토해주세요", "confidence": 0.88}],'
        ' "confidence": 0.88, "needs_review": false, "reason_code": "high_confidence"}'
    )

    def mock_callable(prompt: str) -> str:
        return mock_json

    text = "내일까지 계약서를 검토해주세요."
    with patch.dict(os.environ, {"SKIP_LLM": "false"}):
        result = extract_with_llm(text, {}, llm_callable=mock_callable)

    assert isinstance(result, Card1Extraction)
    assert result.intent_type == IntentType.REQUEST
    assert result.deadline == "2026-05-12"
    assert "계약서" in result.materials
    assert len(result.actions) == 1
    assert result.actions[0].confidence == 0.88


# ── 20: 파이프라인 통합 ───────────────────────────────────────────────────────

def test_extract_card1_pipeline_integration():
    """SKIP_LLM=true 환경에서 전체 파이프라인 end-to-end 검증."""
    text = (
        "안녕하세요. 내일까지 계약서 파일을 보내주시면 감사하겠습니다. "
        "검토 후 회신드리겠습니다."
    )
    with patch.dict(os.environ, {"SKIP_LLM": "true"}):
        result = extract_card1(text)

    assert isinstance(result, Card1Extraction)
    assert result.deadline_raw != "" or len(result.materials) > 0, (
        "마감일 또는 자료가 최소 하나 이상 감지되어야 합니다"
    )
    assert len(result.actions) > 0, "액션이 최소 하나 감지되어야 합니다"
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.sentence_type, SentenceType)
    assert isinstance(result.intent_type, IntentType)


# ── 21~25: 단계 6.4 정정 검증 ────────────────────────────────────────────────

def test_parser_negative_patterns_6():
    """NEGATIVE 패턴 6개 추가 — 없어서/없으니/취소/어렵습니다/보류/연기."""
    cases = [
        ("아직 확인된 사항이 없어서 추가 안내는 어렵습니다.", SentenceType.NEGATIVE),
        ("현재는 결정된 것이 없으니 추후 안내 드리겠습니다.", SentenceType.NEGATIVE),
        ("이번 회의는 취소되었습니다.", SentenceType.NEGATIVE),
        ("해당 일정은 보류됩니다.", SentenceType.NEGATIVE),
        ("계획이 연기됩니다.", SentenceType.NEGATIVE),
        ("해당 건은 더 이상 진행하지 않아도 됩니다.", SentenceType.NEGATIVE),
    ]
    for text, expected_st in cases:
        result = classify_sentence_type(text)
        assert result == expected_st, (
            f"'{text[:40]}...' → 기대={expected_st.name}, 실제={result.name}"
        )


def test_parser_deadline_next_week():
    """'다음 주까지' (요일 없이) 패턴 감지 — 단계 6.3 MISS 수정."""
    cases = [
        "다음 주까지 재발송하겠습니다.",
        "다음 주까지 완료해주세요.",
        "다음 주 월요일까지 보내주세요.",
    ]
    for text in cases:
        found = extract_deadlines(text)
        assert found, f"'{text}' 에서 마감일 미감지"
        assert any("다음" in d for d in found), (
            f"'다음 주까지' 미감지: {found}"
        )


def test_heuristic_classifies_report():
    """heuristic — '드리겠습니다/하겠습니다/예정입니다' → REPORT 분류."""
    from butler_pc_core.card1_extraction.llm_extractor import _heuristic_extraction

    report_cases = [
        "이번 분기 실적을 보고드립니다.",
        "계획서를 내일까지 제출할 예정입니다.",
        "회의 결과를 정리해서 오늘 중에 보내드리겠습니다.",
        "견적서를 수정해서 다음 주까지 재발송하겠습니다.",
    ]
    for text in report_cases:
        hints = {"deadlines": [], "materials": [], "actions": []}
        result = _heuristic_extraction(text, hints)
        assert result.intent_type == IntentType.REPORT, (
            f"'{text[:40]}' → 기대=REPORT, 실제={result.intent_type.value}"
        )


def test_heuristic_polite_request_to_request():
    """단계 8.3: '부탁드립니다/감사하겠습니다' 영역 정중 요청 → REQUEST 분류."""
    from butler_pc_core.card1_extraction.llm_extractor import _heuristic_extraction

    polite_cases = [
        "자료를 받으시면 검토 후 회신 부탁드립니다.",
        "검토가 완료된다면 최종본을 공유해 주시면 감사하겠습니다.",
        "협조 부탁드립니다.",
        "다음 주 미팅 일정 조율해주시면 감사하겠습니다.",
    ]
    for text in polite_cases:
        hints = {"deadlines": [], "materials": [], "actions": []}
        result = _heuristic_extraction(text, hints)
        assert result.intent_type == IntentType.REQUEST, (
            f"'{text[:40]}' → 기대=REQUEST, 실제={result.intent_type.value}"
        )


def test_heuristic_bonaeo_juseyo_to_request():
    """단계 8.3: '보내주세요' 영역 직접 요청 → REQUEST 분류."""
    from butler_pc_core.card1_extraction.llm_extractor import _heuristic_extraction

    cases = [
        "내일까지 계약서 보내주세요.",
        "내일까지 계약서 보내주세요. 검토 부탁드립니다.",
        "다음 주 월요일까지 보고서를 전달해주세요.",
    ]
    for text in cases:
        hints = {"deadlines": [], "materials": [], "actions": []}
        result = _heuristic_extraction(text, hints)
        assert result.intent_type == IntentType.REQUEST, (
            f"'{text[:40]}' → 기대=REQUEST, 실제={result.intent_type.value}"
        )


def test_heuristic_genuine_report_preserved():
    """단계 8.3 회귀 방지: 진짜 보고형('보내드리겠습니다/재발송하겠습니다/처리하겠습니다')은
    여전히 REPORT — '부탁/감사' lookbehind만 우회."""
    from butler_pc_core.card1_extraction.llm_extractor import _heuristic_extraction

    report_cases = [
        "회의 결과를 정리해서 오늘 중에 메일 보내드리겠습니다.",
        "견적서를 수정해서 다음 주까지 재발송하겠습니다.",
        "해당 이슈는 검토 후 다음 주 월요일까지 처리하겠습니다.",
    ]
    for text in report_cases:
        hints = {"deadlines": [], "materials": [], "actions": []}
        result = _heuristic_extraction(text, hints)
        assert result.intent_type == IntentType.REPORT, (
            f"'{text[:40]}' → 기대=REPORT, 실제={result.intent_type.value}"
        )


def test_heuristic_classifies_no_action():
    """heuristic — 부정/취소/없습니다 → NO_ACTION 분류."""
    from butler_pc_core.card1_extraction.llm_extractor import _heuristic_extraction

    no_action_cases = [
        "오늘은 특별한 일정이 없습니다.",
        "이번 회의는 취소되었습니다.",
        "아직 확인된 사항이 없어서 추가 안내는 어렵습니다.",
        "현재는 결정된 것이 없으니 추후 안내 드리겠습니다.",
        "해당 건은 더 이상 진행하지 않아도 됩니다.",
    ]
    for text in no_action_cases:
        hints = {"deadlines": [], "materials": [], "actions": []}
        result = _heuristic_extraction(text, hints)
        assert result.intent_type == IntentType.NO_ACTION, (
            f"'{text[:40]}' → 기대=NO_ACTION, 실제={result.intent_type.value}"
        )


def test_calibration_corrected():
    """Platt-style 보정 후 heuristic 신뢰도 범위 및 calibration 특성 검증."""
    from butler_pc_core.card1_extraction.confidence import _BASE_SCORE

    assert _BASE_SCORE == 0.35, f"Platt 보정 base 기대=0.35, 실제={_BASE_SCORE}"

    # 증거 없음 → 최저 신뢰도 (과신뢰 억제)
    low_factors = ConfidenceFactors(
        action_verb_count=0, deadline_found=False, deadline_claimed=False,
        material_count=0, action_count=0, hallucination_count=0,
    )
    low_conf = compute_card1_confidence(low_factors)
    assert low_conf < 0.40, f"증거 없을 때 신뢰도 0.40 미만 기대, 실제: {low_conf}"

    # 증거 풍부 → 적절한 신뢰도 (0.85~0.90 수렴)
    high_factors = ConfidenceFactors(
        action_verb_count=2, deadline_found=True, deadline_claimed=True,
        material_count=2, action_count=2, hallucination_count=0,
    )
    high_conf = compute_card1_confidence(high_factors)
    assert 0.80 <= high_conf <= 0.95, (
        f"증거 풍부 시 신뢰도 0.80~0.95 기대, 실제: {high_conf}"
    )

    # hallucination → 신뢰도 감소 확인
    penalized = ConfidenceFactors(
        action_verb_count=2, deadline_found=True, deadline_claimed=True,
        material_count=1, action_count=1, hallucination_count=2,
    )
    pen_conf = compute_card1_confidence(penalized)
    assert pen_conf < high_conf, "hallucination penalty 미작동"
