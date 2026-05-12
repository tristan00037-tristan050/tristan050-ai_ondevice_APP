"""단계 6.5.4 — 5개 패치 단위 테스트 (알고리즘 팀 지침).

Patch A — DeadlineType Enum (6종)
Patch B — disqualifier 패턴 + classify_deadline_candidate
Patch C — Verifier verify_deadline (type-aware Block 7)
Patch D — confidence aggregation 변경 (absent skip + hard gate + weighted)
Patch E — REPORT_MARKERS 확장 (18 → 22) + component fit 정책
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from butler_pc_core.card1_extraction.deadline_types import (
    DeadlineType,
    DEADLINE_INQUIRY_PATTERNS, URGENCY_ONLY_PATTERNS, CONDITION_ONLY_PATTERNS,
    classify_deadline_candidate, is_valid_deadline_type,
)
from butler_pc_core.card1_extraction.verifier import (
    verify_deadline, has_deadline_evidence,
    BLOCK_FALSE_DEADLINE_NO_EVIDENCE, apply_hard_rules,
)
from butler_pc_core.card1_extraction.confidence import (
    AUTO_APPLY_THRESHOLDS, COMPONENT_WEIGHTS,
    aggregate_confidence, weighted_final_confidence, should_auto_apply,
)
from butler_pc_core.card1_extraction.intent_normalizer import REPORT_MARKERS
from butler_pc_core.card1_extraction.contracts import (
    Card1Extraction, ExtractedAction, IntentType, SentenceType,
)


# ── Patch A — DeadlineType Enum ────────────────────────────────────────

def test_deadline_type_enum_has_6_members():
    members = {m.value for m in DeadlineType}
    assert members == {"none", "hard_deadline", "soft_deadline",
                       "deadline_inquiry", "urgency", "condition"}


def test_deadline_type_valid_subset():
    assert is_valid_deadline_type(DeadlineType.HARD_DEADLINE) is True
    assert is_valid_deadline_type(DeadlineType.SOFT_DEADLINE) is True
    for invalid in (DeadlineType.NONE, DeadlineType.DEADLINE_INQUIRY,
                    DeadlineType.URGENCY, DeadlineType.CONDITION):
        assert is_valid_deadline_type(invalid) is False


# ── Patch B — classify_deadline_candidate ───────────────────────────────

def test_classify_inquiry_card1_002():
    assert classify_deadline_candidate("보고서 검토 언제까지 가능하신가요?") \
        == DeadlineType.DEADLINE_INQUIRY


def test_classify_urgency_card1_023():
    assert classify_deadline_candidate("지금 바로 연락해주세요") \
        == DeadlineType.URGENCY


def test_classify_condition_card1_039():
    assert classify_deadline_candidate("계약서 수정이 완료되면 보내주세요") \
        == DeadlineType.CONDITION


def test_classify_hard_deadline():
    assert classify_deadline_candidate("금요일까지 제출") == DeadlineType.HARD_DEADLINE
    assert classify_deadline_candidate("회의 전까지 회신") == DeadlineType.HARD_DEADLINE


def test_classify_soft_deadline():
    assert classify_deadline_candidate("오늘 중으로 처리") == DeadlineType.SOFT_DEADLINE
    assert classify_deadline_candidate("이번 주 중 마감") == DeadlineType.SOFT_DEADLINE


def test_classify_none():
    assert classify_deadline_candidate("회의록 검토") == DeadlineType.NONE
    assert classify_deadline_candidate("") == DeadlineType.NONE


def test_classify_priority_inquiry_over_other():
    """inquiry 우선 — '언제까지 가능'은 '까지'보다 우선."""
    assert classify_deadline_candidate("언제까지 가능하신가요?") \
        == DeadlineType.DEADLINE_INQUIRY


# ── Patch C — verify_deadline (type-aware) ─────────────────────────────

def test_verify_deadline_no_text_passes():
    ok, why = verify_deadline(None, None, "원문")
    assert ok is True
    assert why == "NO_DEADLINE"


def test_verify_deadline_evidence_not_in_source_blocks():
    ok, why = verify_deadline("내일까지", "내일까지 마감", "전혀 다른 원문")
    assert ok is False
    assert why == "DEADLINE_EVIDENCE_NOT_IN_SOURCE"


def test_verify_deadline_blocks_inquiry():
    src = "보고서 검토 언제까지 가능하신가요?"
    ok, why = verify_deadline("언제까지 가능하신가요", src, src)
    assert ok is False
    assert "deadline_inquiry" in why


def test_verify_deadline_blocks_urgency():
    src = "클라이언트에게 지금 바로 연락해주세요."
    ok, why = verify_deadline("지금 바로", src, src)
    assert ok is False
    assert "urgency" in why


def test_verify_deadline_blocks_condition():
    src = "계약서 수정이 완료되면 바로 보내주세요."
    ok, why = verify_deadline("수정이 완료되면", src, src)
    assert ok is False
    assert "condition" in why


def test_verify_deadline_passes_hard():
    src = "금요일까지 회의록 보내주세요."
    ok, why = verify_deadline("금요일까지", src, src)
    assert ok is True
    assert "hard_deadline" in why


def test_block_7_applies_inquiry_in_apply_hard_rules():
    """card1_002 시나리오 — 의문문 inquiry 차단."""
    src = "보고서 검토 언제까지 가능하신가요?"
    action = ExtractedAction(
        action_text="보고서 검토",
        source_evidence=src,
        deadline_text="언제까지 가능하신가요",
    )
    ex = Card1Extraction(
        intent="검토", intent_type=IntentType.QUESTION,
        deadline=None, deadline_raw="언제까지 가능하신가요",
        materials=["보고서"], actions=[action],
        sentence_type=SentenceType.INTERROGATIVE,
        confidence=0.7, needs_review=True, reason_code="",
    )
    rep = apply_hard_rules(ex, src, confidence=0.8, schema_valid=True)
    assert BLOCK_FALSE_DEADLINE_NO_EVIDENCE in rep.errors
    assert rep.extraction.deadline_raw == ""


def test_block_7_applies_urgency_in_apply_hard_rules():
    """card1_023 시나리오 — urgency 차단."""
    src = "클라이언트에게 지금 바로 연락해주세요."
    action = ExtractedAction(
        action_text="클라이언트 연락",
        source_evidence=src,
        deadline_text="지금 바로",
    )
    ex = Card1Extraction(
        intent="연락", intent_type=IntentType.REQUEST,
        deadline=None, deadline_raw="지금 바로",
        materials=[], actions=[action],
        sentence_type=SentenceType.IMPERATIVE,
        confidence=0.7, needs_review=True, reason_code="",
    )
    rep = apply_hard_rules(ex, src, confidence=0.8, schema_valid=True)
    assert BLOCK_FALSE_DEADLINE_NO_EVIDENCE in rep.errors
    assert rep.extraction.deadline_raw == ""


def test_block_7_applies_condition_in_apply_hard_rules():
    """card1_039 시나리오 — condition 차단."""
    src = "계약서 수정이 완료되면 바로 보내주세요."
    action = ExtractedAction(
        action_text="계약서 보내기",
        source_evidence=src,
        deadline_text="수정이 완료되면",
    )
    ex = Card1Extraction(
        intent="보내기", intent_type=IntentType.REQUEST,
        deadline=None, deadline_raw="수정이 완료되면",
        materials=["계약서"], actions=[action],
        sentence_type=SentenceType.CONDITIONAL,
        confidence=0.7, needs_review=True, reason_code="",
    )
    rep = apply_hard_rules(ex, src, confidence=0.8, schema_valid=True)
    assert BLOCK_FALSE_DEADLINE_NO_EVIDENCE in rep.errors


# ── Patch D — Confidence aggregation ───────────────────────────────────

def test_auto_apply_thresholds_5keys():
    expected = {"action", "intent", "deadline", "material", "final_weighted"}
    assert set(AUTO_APPLY_THRESHOLDS.keys()) == expected
    assert AUTO_APPLY_THRESHOLDS["action"] == 0.85
    assert AUTO_APPLY_THRESHOLDS["intent"] == 0.75
    assert AUTO_APPLY_THRESHOLDS["deadline"] == 0.85
    assert AUTO_APPLY_THRESHOLDS["material"] == 0.75
    assert AUTO_APPLY_THRESHOLDS["final_weighted"] == 0.80


def test_aggregate_skips_absent_fields():
    """deadline absent 면 deadline_conf 가 aggregation 영향 없음."""
    components = {"action": 0.9, "intent": 0.85, "deadline": 0.30, "material": 0.50}
    # deadline absent → 무시
    out = aggregate_confidence(components, present_fields={"material"})
    # active = action + intent + material → min(0.9, 0.85, 0.5)
    assert out == 0.5


def test_weighted_final_normalizes_when_absent():
    """deadline absent 시 가중치 재정규화."""
    components = {"action": 1.0, "intent": 1.0}
    gates = {"schema_ok": True, "verifier_ok": True, "evidence_ok": True}
    out = weighted_final_confidence(components, present_fields=set(), gates=gates)
    # action(0.45) + intent(0.30) → normalize to 1.0 → final=1.0
    assert abs(out - 1.0) < 1e-3


def test_weighted_final_hard_gate_blocks():
    components = {"action": 1.0, "intent": 1.0}
    gates = {"schema_ok": False, "verifier_ok": True, "evidence_ok": True}
    out = weighted_final_confidence(components, present_fields=set(), gates=gates)
    assert out == 0.0


def test_should_auto_apply_threshold_logic():
    gates = {"schema_ok": True, "verifier_ok": True, "evidence_ok": True}
    # 모두 통과
    comp = {"action": 0.9, "intent": 0.8, "deadline": 0.9, "material": 0.8}
    ok, _ = should_auto_apply(comp, {"deadline", "material"}, 0.85, gates)
    assert ok is True

    # action 미달
    comp_bad = {"action": 0.7, "intent": 0.9, "deadline": 0.9, "material": 0.9}
    ok, why = should_auto_apply(comp_bad, {"deadline", "material"}, 0.85, gates)
    assert ok is False
    assert why == "action_below_threshold"

    # deadline absent — deadline threshold 무시
    comp_no_dl = {"action": 0.9, "intent": 0.8, "deadline": 0.2, "material": 0.8}
    ok_skip, _ = should_auto_apply(comp_no_dl, {"material"}, 0.85, gates)
    assert ok_skip is True


def test_should_auto_apply_final_threshold():
    """final_weighted < 0.80 → block."""
    gates = {"schema_ok": True, "verifier_ok": True, "evidence_ok": True}
    comp = {"action": 0.9, "intent": 0.8, "deadline": 0.9, "material": 0.8}
    ok, why = should_auto_apply(comp, {"deadline", "material"}, 0.79, gates)
    assert ok is False
    assert why == "final_below_threshold"


# ── Patch E — REPORT_MARKERS 확장 (18 → 22) ────────────────────────────

def test_report_markers_count_22():
    assert len(REPORT_MARKERS) == 22


def test_report_markers_new_4_present():
    new4 = ["보내드리겠습니다", "재발송하겠습니다",
            "처리하겠습니다", "공유해드립니다"]
    for marker in new4:
        assert marker in REPORT_MARKERS, f"{marker} 누락"
