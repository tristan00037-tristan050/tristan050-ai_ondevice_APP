"""Codex P1-2 V8/V9 ordering 회귀 (옵션 B+C): candidate→verifier→final."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.verifier_card1 import apply_card1_hard_rules
from scripts.eval.run_card1_six_five_six import _mode_d_compute_auto_candidate


def _base_pred(**over):
    pred = {
        "intent_type":                "REQUEST",
        "action_required":            True,
        "answer_required":            False,
        "auto_apply_allowed":         False,
        "deadline_type":              "NONE",
        "deadline_is_actionable":     False,
        "intent_confidence_calibrated": 0.9,
        "action_confidence_calibrated": 0.95,
        "raw_intent_confidence":      0.8,
        "raw_action_confidence":      0.85,
        "actions":                    [{"action_text": "검토",
                                         "evidence":    "검토 부탁드립니다"}],
        "slice_tags":                 [],
    }
    pred.update(over)
    return pred


CAL = {"auto_apply_threshold": {"intent": 0.75, "action": 0.85},
       "targets": {"intent": {"A": -4, "B": 2},
                    "action": {"A": -4, "B": 2}}}


def test_risky_high_confidence_candidate_is_blocked_before_auto_apply():
    """V9 우회 차단: 높은 confidence + risky 패턴 → candidate=True 지만 V9 fires."""
    pred = _base_pred(slice_tags=["risky_action", "external_send"])
    auto_candidate = _mode_d_compute_auto_candidate(pred, CAL)
    assert auto_candidate is True
    vres = apply_card1_hard_rules(
        sample_id="card1_test_risky", text="외부 전송 부탁드립니다",
        pred=pred, schema_valid=True, base_verifier_errors=[],
        auto_apply_candidate=auto_candidate,
    )
    assert any(e.startswith("V9/") for e in vres.errors)
    # 최종 결정
    final_auto = auto_candidate and vres.error_count == 0
    assert final_auto is False


def test_safe_high_confidence_candidate_can_auto_apply():
    """과차단 방지: 안전한 high-confidence 행은 candidate + verifier 통과 → final=True."""
    pred = _base_pred(slice_tags=["document_task"])
    auto_candidate = _mode_d_compute_auto_candidate(pred, CAL)
    assert auto_candidate is True
    vres = apply_card1_hard_rules(
        sample_id="card1_test_safe", text="회의록 정리해서 공유 부탁드립니다",
        pred=pred, schema_valid=True, base_verifier_errors=[],
        auto_apply_candidate=auto_candidate,
    )
    assert vres.error_count == 0
    final_auto = auto_candidate and vres.error_count == 0
    assert final_auto is True


def test_non_gold_equivalent_candidate_is_blocked_by_v8():
    """V8: candidate=True 지만 intent ∉ {REQUEST,REPORT,NO_ACTION} → V8 차단."""
    # candidate 산출 시 intent ∈ {REQUEST, COMMAND}. COMMAND 는 SAFE_INTENT_FOR_AUTO 아님.
    pred = _base_pred(intent_type="COMMAND", slice_tags=["document_task"])
    auto_candidate = _mode_d_compute_auto_candidate(pred, CAL)
    assert auto_candidate is True
    vres = apply_card1_hard_rules(
        sample_id="card1_test_cmd", text="문서 정리하세요",
        pred=pred, schema_valid=True, base_verifier_errors=[],
        auto_apply_candidate=auto_candidate,
    )
    assert any(e.startswith("V8/") for e in vres.errors)
    final_auto = auto_candidate and vres.error_count == 0
    assert final_auto is False


def test_v8_v9_skipped_when_no_candidate():
    """candidate=False 이면 V8/V9 검사 없음 (위험 row 라도 verifier errors 미발생)."""
    pred = _base_pred(intent_confidence_calibrated=0.1,
                      action_confidence_calibrated=0.1,
                      slice_tags=["risky_action"])
    auto_candidate = _mode_d_compute_auto_candidate(pred, CAL)
    assert auto_candidate is False
    vres = apply_card1_hard_rules(
        sample_id="card1_test_low", text="외부 전송",
        pred=pred, schema_valid=True, base_verifier_errors=[],
        auto_apply_candidate=auto_candidate,
    )
    # V8/V9 검사 안 됨
    assert not any(e.startswith("V8/") for e in vres.errors)
    assert not any(e.startswith("V9/") for e in vres.errors)
