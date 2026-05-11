"""test_card1_extraction.py — 단계 5: card1_extraction 모듈 검증 (20 tests)."""
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
    # base(0.40) + intent(0.25) + deadline(0.25) + material(0.10) + action(0.10) = 1.10 → 1.0
    assert conf >= 0.90, f"evidence 충분할 때 신뢰도 0.90+ 기대, 실제: {conf}"


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
    assert base_conf - penalized_conf >= 0.38, (
        f"penalty 2건(-0.40)이 반영되어야 합니다: diff={base_conf - penalized_conf:.3f}"
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
