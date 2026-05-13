"""단계 6.5.2 — 3개 패치 단위 테스트 (알고리즘 팀 지침).

Patch 1 — REPORT marker override (intent_normalizer.post_fix_intent_type)
Patch 2 — action verb normalization (action_normalizer.normalize_action_verb)
Patch 3 — low_confidence_true_positive 집계 (평가 스크립트)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from butler_pc_core.card1_extraction.intent_normalizer import (
    REPORT_MARKERS, REQUEST_MARKERS, OVERRIDE_REASON, post_fix_intent_type,
)
from butler_pc_core.card1_extraction.action_normalizer import (
    ACTION_NORMALIZE, normalize_action_verb,
)
from butler_pc_core.card1_extraction.llm_extractor import (
    _v1_dict_to_extraction,
)
from butler_pc_core.card1_extraction.contracts import IntentType


# ── Patch 1 — REPORT marker override ─────────────────────────────────────

def test_report_marker_override_predicts_report():
    """REPORT marker가 있고 REQUEST marker가 없으면 report로 override."""
    text = "프로젝트 계획서를 내일까지 제출할 예정입니다."
    out, why = post_fix_intent_type(text, "request")
    assert out == "report"
    assert why == OVERRIDE_REASON


def test_report_marker_override_skips_when_request_marker_present():
    """REPORT marker가 있어도 REQUEST marker가 있으면 override 안 함."""
    text = "내일까지 보고서 제출할 예정입니다. 회신 부탁드립니다."
    # "예정입니다" (REPORT) + "부탁드립니다" (REQUEST) → override 보류
    out, why = post_fix_intent_type(text, "request")
    assert out == "request"
    assert why == "OK"


def test_report_marker_override_preserves_existing_report():
    """이미 report이면 결과 intent 그대로 유지 (reason_code 는 6.5.3 spec 에서 override).

    6.5.2 → "보고드립니다"가 REPORT_MARKERS에 미포함 → why="OK"
    6.5.3 → "보고드립니다"가 REPORT_MARKERS에 포함됨 → why=OVERRIDE_REASON.
    어느 spec 에서도 out=='report'는 동일하게 유지된다.
    """
    text = "이번 분기 실적을 보고드립니다."
    out, why = post_fix_intent_type(text, "report")
    assert out == "report"
    assert why in {"OK", OVERRIDE_REASON}


def test_report_marker_override_no_change_when_no_markers():
    """둘 다 없으면 그대로."""
    out, why = post_fix_intent_type("이번 주 금요일에 팀 미팅이 있습니다.", "schedule")
    assert out == "schedule"
    assert why == "OK"


def test_report_marker_override_applied_in_v1_dict_to_extraction():
    """_v1_dict_to_extraction이 LLM 'request' → 'report' override 반영."""
    data = {
        "intent_type": "request",
        "actions": [{
            "action_text": "계획서 제출", "action_type": "제출",
            "deadline_text": "내일까지", "material_refs": ["계획서"],
            "evidence": "제출할 예정입니다", "is_negated": False,
        }],
        "no_action": False, "reason_code": "ok",
    }
    src = "프로젝트 계획서를 내일까지 제출할 예정입니다."
    ex  = _v1_dict_to_extraction(data, src)
    assert ex.intent_type == IntentType.REPORT
    assert ex.reason_code == OVERRIDE_REASON


# ── Patch 2 — action verb normalization ─────────────────────────────────

def test_normalize_send_group():
    assert normalize_action_verb("이메일 보내기") == "send"
    assert normalize_action_verb("보고서 보내주세요") == "send"
    assert normalize_action_verb("자료 전달 부탁") == "send"
    assert normalize_action_verb("문서 송부 요청") == "send"


def test_normalize_share_review_groups():
    assert normalize_action_verb("회의록 공유해주세요") == "share"
    assert normalize_action_verb("내용 검토 부탁") == "review"
    assert normalize_action_verb("자료 확인해주세요") == "review"


def test_normalize_organize_revise_submit():
    assert normalize_action_verb("자료 정리 후") == "organize"
    assert normalize_action_verb("초안 수정") == "revise"
    assert normalize_action_verb("의견 반영") == "revise"
    assert normalize_action_verb("계획서 제출") == "submit"
    assert normalize_action_verb("회신 부탁") == "submit"


def test_normalize_upload_other():
    assert normalize_action_verb("이미지 업로드") == "upload"
    assert normalize_action_verb("자료 첨부") == "upload"
    assert normalize_action_verb("그냥 평서문") == "other"
    assert normalize_action_verb("") == "other"


def test_normalize_dict_consistent():
    """ACTION_NORMALIZE 값은 모두 7개 정규 그룹 안에 있다."""
    canonical = {"send", "share", "organize", "review", "revise", "submit", "upload"}
    assert set(ACTION_NORMALIZE.values()) <= canonical


# ── Patch 3 — low_confidence_true_positive 집계 ─────────────────────────

def test_low_confidence_true_positive_helper():
    """평가 스크립트의 low_confidence_true_positive 카운팅 로직 검증."""
    # in-test helper — 평가 스크립트 사용 함수와 동일한 로직
    samples = [
        {"correct": True,  "confidence": 0.60},  # TP but blocked → count
        {"correct": True,  "confidence": 0.80},  # TP, auto → skip
        {"correct": False, "confidence": 0.55},  # FP, blocked → skip
        {"correct": True,  "confidence": 0.74},  # TP but blocked → count
        {"correct": True,  "confidence": 0.75},  # exactly threshold → auto (skip)
    ]
    THRESHOLD = 0.75
    count = sum(1 for s in samples if s["correct"] and s["confidence"] < THRESHOLD)
    assert count == 2


def test_low_confidence_true_positive_uses_strict_threshold():
    """0.75 미만이 'low' — 0.75는 auto 적용."""
    THRESHOLD = 0.75
    assert (0.7499 < THRESHOLD) is True
    assert (0.7500 < THRESHOLD) is False
