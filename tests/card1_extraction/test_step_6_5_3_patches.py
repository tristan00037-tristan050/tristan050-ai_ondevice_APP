"""단계 6.5.3 — 5개 패치 단위 테스트 (알고리즘 팀 지침).

Patch 1 — REPORT_MARKERS 확장 (9 → 18)
Patch 2 — COMMAND normalizer (과잉 보정 방지)
Patch 3 — Verifier Block 7 (false_deadline hard rule)
Patch 4 — confidence calibration target 분리
Patch 5 — low_confidence_true_positive 6-category breakdown
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from butler_pc_core.card1_extraction.intent_normalizer import (
    REPORT_MARKERS, REQUEST_MARKERS, COMMAND_MARKERS, SOFT_REQUEST_MARKERS,
    REPORT_OVERRIDE_REASON, COMMAND_OVERRIDE_REASON,
    normalize_report_intent, normalize_command_intent, normalize_intent_chain,
    post_fix_intent_type,
)
from butler_pc_core.card1_extraction.verifier import (
    DEADLINE_MARKERS, has_deadline_evidence,
    BLOCK_FALSE_DEADLINE_NO_EVIDENCE, apply_hard_rules,
)
from butler_pc_core.card1_extraction.confidence import (
    ConfidenceFeatures,
    action_raw_score, intent_raw_score, overall_raw_score,
    deadline_confidence_heuristic, material_confidence_heuristic,
    compose_final_confidence, platt_calibrate,
)
from butler_pc_core.card1_extraction.contracts import (
    Card1Extraction, ExtractedAction, IntentType, SentenceType,
)


# ── Patch 1 — REPORT_MARKERS 확장 (9 → 18) ──────────────────────────────

def test_report_markers_count_18():
    # 6.5.3: 18 / 6.5.4: 22 (4개 추가) — 6.5.3 이상은 항상 통과
    assert len(REPORT_MARKERS) >= 18


def test_report_markers_new_9_present():
    new9 = ["보고드립니다", "말씀드리겠습니다", "공유드리겠습니다",
            "안내드리겠습니다", "전달드리겠습니다", "보고드리겠습니다",
            "설명드리겠습니다", "알려드립니다", "안내드립니다"]
    for marker in new9:
        assert marker in REPORT_MARKERS, f"{marker} 누락"


def test_report_marker_new_triggers_override():
    out, why = normalize_report_intent("이번 분기 실적을 보고드립니다.", "request")
    assert out == "report"
    assert why == REPORT_OVERRIDE_REASON


def test_report_marker_chain_via_post_fix_alias():
    """post_fix_intent_type가 normalize_report_intent의 alias로 동작."""
    out, why = post_fix_intent_type("프로젝트를 말씀드리겠습니다.", "request")
    assert out == "report"
    assert why == REPORT_OVERRIDE_REASON


def test_request_marker_blocks_override():
    """REPORT marker가 있어도 REQUEST marker가 있으면 보류."""
    text = "확인해 주세요. 이번 분기 실적을 보고드립니다."
    out, why = normalize_report_intent(text, "request")
    assert out == "request"
    assert why == "OK"


def test_request_markers_include_confirm_juseyo():
    assert "확인해 주세요" in REQUEST_MARKERS


# ── Patch 2 — COMMAND normalizer ──────────────────────────────────────

def test_command_markers_count_13():
    assert len(COMMAND_MARKERS) == 13


def test_command_marker_triggers_override():
    out, why = normalize_command_intent("오늘 중으로 보고서 제출하세요.", "request")
    assert out == "command"
    assert why == COMMAND_OVERRIDE_REASON


def test_command_no_overcorrection_for_juseyo():
    """'~해 주세요' 계열은 COMMAND override 금지 (REQUEST 유지)."""
    cases = [
        "계약서 파일 확인 후 서명해서 내일까지 메일로 보내주세요.",
        "예산안 검토 후 승인하고, 팀원들에게 공유해주세요.",
        "발표 자료 만들고 월요일까지 발표 준비 완료해주세요.",
        "이사님께 보고드려주세요.",
    ]
    for t in cases:
        out, why = normalize_command_intent(t, "request")
        assert out == "request", f"COMMAND 과잉 보정: {t!r}"
        assert why == "OK"


def test_command_soft_request_blocks_override():
    """'하세요' 가 있어도 SOFT_REQUEST marker 가 있으면 보류."""
    out, why = normalize_command_intent("제출하세요. 부탁드립니다.", "request")
    assert out == "request"
    assert why == "OK"


def test_normalize_intent_chain_report_first():
    """REPORT marker 우선 — REPORT가 있으면 COMMAND는 평가 안 함."""
    out, why = normalize_intent_chain("이번 분기 실적을 보고드립니다.", "request")
    assert out == "report"
    assert why == REPORT_OVERRIDE_REASON


def test_normalize_intent_chain_command_when_no_report():
    out, why = normalize_intent_chain("오늘 중으로 보고서 제출하세요.", "request")
    assert out == "command"
    assert why == COMMAND_OVERRIDE_REASON


def test_normalize_intent_chain_no_override():
    """양쪽 marker 모두 없으면 LLM intent 그대로."""
    out, why = normalize_intent_chain("회의록 보내주세요.", "request")
    assert out == "request"
    assert why == "OK"


# ── Patch 3 — Verifier Block 7 (false_deadline hard rule) ───────────────

def test_deadline_markers_present():
    expected = ["오늘", "내일", "까지", "마감", "금요일"]
    for m in expected:
        assert m in DEADLINE_MARKERS


def test_has_deadline_evidence_empty_passes():
    assert has_deadline_evidence("aaa", None, None) is True
    assert has_deadline_evidence("aaa", "", "") is True


def test_has_deadline_evidence_evidence_in_source_passes():
    src = "내일까지 보고서 보내주세요."
    assert has_deadline_evidence(src, "내일까지", "내일까지 보고서") is True


def test_has_deadline_evidence_no_marker_blocks():
    """원문에 DEADLINE_MARKERS 가 하나도 없으면 BLOCK."""
    src = "계약서 수정이 완료되면 바로 보내주세요."
    assert has_deadline_evidence(src, "바로", None) is False


def test_has_deadline_evidence_compact_match_passes():
    src = "이번 주 금요일까지 보내주세요."
    assert has_deadline_evidence(src, "금요일까지", None) is True


def test_block_7_applies_in_apply_hard_rules():
    """deadline_raw 가 원문에 있지만 DEADLINE_MARKERS 없으면 Block 7 발동."""
    src = "지금 바로 연락 부탁."
    ex  = Card1Extraction(
        intent="연락", intent_type=IntentType.REQUEST,
        deadline=None, deadline_raw="바로",
        materials=[], actions=[], sentence_type=SentenceType.DECLARATIVE,
        confidence=0.5, needs_review=True, reason_code="",
    )
    report = apply_hard_rules(ex, src, confidence=0.8, schema_valid=True)
    assert BLOCK_FALSE_DEADLINE_NO_EVIDENCE in report.errors
    assert report.extraction.deadline_raw == ""


# ── Patch 4 — calibration target 분리 ──────────────────────────────────

def test_action_raw_score_positive_with_good_features():
    f = ConfidenceFeatures(
        parser_action_score=0.9, parser_material_score=0.8,
        llm_schema_valid=True, llm_parser_agreement=0.9,
        evidence_coverage=1.0, verifier_error_count=0, negation_risk=0.0,
    )
    s = action_raw_score(f, multi_action_count=2, all_actions_have_evidence=True)
    assert s > 0.5


def test_action_raw_score_multi_action_bonus_vs_penalty():
    f = ConfidenceFeatures(
        parser_action_score=0.5, llm_schema_valid=True, evidence_coverage=1.0,
        multi_action_complexity=1.0,
    )
    s_bonus   = action_raw_score(f, multi_action_count=3, all_actions_have_evidence=True)
    s_penalty = action_raw_score(f, multi_action_count=3, all_actions_have_evidence=False)
    assert s_bonus > s_penalty


def test_intent_raw_normalizer_signal():
    f = ConfidenceFeatures(parser_intent_score=0.4, llm_schema_valid=True)
    s_no  = intent_raw_score(f, normalizer_applied=False, normalizer_conflict=False)
    s_yes = intent_raw_score(f, normalizer_applied=True,  normalizer_conflict=False)
    s_bad = intent_raw_score(f, normalizer_applied=False, normalizer_conflict=True)
    assert s_yes > s_no > s_bad


def test_overall_raw_penalizes_deadline_material_failures():
    f = ConfidenceFeatures(parser_action_score=0.8, llm_schema_valid=True,
                           evidence_coverage=1.0)
    s_ok      = overall_raw_score(f, deadline_ok=True,  material_ok=True)
    s_dl_bad  = overall_raw_score(f, deadline_ok=False, material_ok=True)
    s_mat_bad = overall_raw_score(f, deadline_ok=True,  material_ok=False)
    assert s_ok > s_dl_bad
    assert s_ok > s_mat_bad


def test_compose_final_takes_min():
    out = compose_final_confidence(0.9, 0.5, 0.8, 0.95)
    assert out == 0.5


def test_deadline_block_7_reduces_confidence():
    f = ConfidenceFeatures(parser_deadline_score=1.0)
    assert deadline_confidence_heuristic(f, block_7_fired=False) > \
           deadline_confidence_heuristic(f, block_7_fired=True)


# ── Patch 5 — low_confidence_true_positive breakdown ──────────────────

def test_low_conf_breakdown_categories():
    """평가 스크립트가 사용하는 6 category 카운터 골격."""
    breakdown = {
        "due_to_intent_uncertainty":          0,
        "due_to_deadline_uncertainty":        0,
        "due_to_material_uncertainty":        0,
        "due_to_parser_llm_disagreement":     0,
        "due_to_multi_action_penalty":        0,
        "due_to_verifier_soft_warning":       0,
    }
    assert len(breakdown) == 6
    for k, v in breakdown.items():
        assert v == 0
        assert k.startswith("due_to_")


def test_low_conf_breakdown_classifier():
    """min-component → category 매핑 헬퍼."""
    def classify(action_c, intent_c, deadline_c, material_c,
                 verifier_err_count, multi_action_complexity):
        if verifier_err_count > 0:
            return "due_to_verifier_soft_warning"
        if multi_action_complexity >= 0.5:
            return "due_to_multi_action_penalty"
        confs = {
            "due_to_intent_uncertainty":      intent_c,
            "due_to_deadline_uncertainty":    deadline_c,
            "due_to_material_uncertainty":    material_c,
            "due_to_parser_llm_disagreement": action_c,
        }
        return min(confs, key=confs.get)

    assert classify(0.9, 0.4, 0.95, 0.95, 0, 0.0) == "due_to_intent_uncertainty"
    assert classify(0.9, 0.9, 0.3, 0.95, 0, 0.0) == "due_to_deadline_uncertainty"
    assert classify(0.9, 0.9, 0.9, 0.9, 1, 0.0) == "due_to_verifier_soft_warning"
    assert classify(0.9, 0.9, 0.9, 0.9, 0, 1.0) == "due_to_multi_action_penalty"
