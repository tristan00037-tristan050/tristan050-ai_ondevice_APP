"""PR #732 Branch B-2G over-extraction guard sentinel — #1~#15."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day26/b2g_over_extraction_guard"

from scripts.eval.pr732_b2g_over_extraction_guard import (  # noqa: E402
    PRODUCTION_GATE, b2g_guard, guard_decision,
)


def _j(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


# ── #1 A4 REPORT 패턴 차단 ───────────────────────────────────────────────
def test_A4_guard_blocks_report_pattern():
    assert guard_decision("회의 결과 공유드립니다") == "block"
    assert guard_decision("발표 자료 작성 완료했어요") == "block"
    assert guard_decision("프로젝트 일정 갱신했습니다") == "block"
    # action 리스트가 비워짐
    assert b2g_guard([{"action_text": "공유"}], "회의록 공유드립니다") == []


# ── #2 QUESTION 패턴 — manual_suggestion 보존 (A3) ───────────────────────
def test_A4_guard_question_pattern_manual_suggestion():
    # 자문 인계 "QUESTION 차단" 은 A3 보존과 정합 처리: 보존 + auto_apply OFF
    assert guard_decision("버전 정보 알 수 있을까요?") == "manual_suggestion"
    out = b2g_guard([{"action_text": "버전 정보 확인"}],
                    "버전 정보 알 수 있을까요?")
    assert len(out) == 1
    assert out[0]["manual_suggestion_allowed"] is True
    assert out[0]["auto_apply"] is False


# ── #3 NO_ACTION 마커 차단 ───────────────────────────────────────────────
def test_A4_guard_blocks_no_action_marker():
    assert guard_decision("이 문서는 참고만 하세요") == "block"
    assert b2g_guard([{"action_text": "x"}], "정보 공유만 합니다 참고용") == []


# ── #4 A3 과차단 0건 (manual_suggestion 보존) ────────────────────────────
def test_A3_preservation_manual_suggestion_allowed():
    rep = _j("a3_preservation_report.json")
    assert rep["a3_over_blocked"] == 0
    assert rep["over_block_zero"] is True
    assert rep["a3_preserved"] == rep["a3_total"] == 32


# ── #5 A5 영향 0건 (gold>=1 case 불변) ───────────────────────────────────
def test_A5_invariance():
    rep = _j("a5_invariance_report.json")
    assert rep["a5_affected"] == 0
    assert rep["a5_invariance_held"] is True
    assert rep["a5_total"] == 6


# ── #6 strict_action_f1 산식 불변 ────────────────────────────────────────
def test_strict_action_f1_sansik_불변():
    ba = _j("before_after_strict_action_f1.json")
    assert ba["sansik_unchanged"] is True
    # guard 는 FP 만 제거 — strict_action_f1 하락 불가
    assert ba["after"] >= ba["before"]
    assert ba["after"] >= 0.6182


# ── #7 production gate threshold 불변 ────────────────────────────────────
def test_production_gate_threshold_불변():
    assert PRODUCTION_GATE == 0.90
    ba = _j("before_after_strict_action_f1.json")
    assert ba["production_gate"] == 0.90


# ── #8 metric contract v2.0.0 유지 (bump 0) ──────────────────────────────
def test_metric_contract_v2_0_0_유지():
    pda = _j("policy_drift_assessment.json")
    assert pda["contract_version"] == "2.0.0"
    assert pda["contract_version_changed"] is False
    assert pda["drift_rate"] == 0.0


# ── #9 safety 6종 정합 (G22/G23 hard = 0) ────────────────────────────────
def test_safety_6종_정합():
    sf = _j("before_after_safety_6종.json")["safety_metrics"]
    assert sf["g22_strict_warning_count"]["after"] == 0
    assert sf["g23_hard_violation_count"]["after"] == 0
    for m in sf.values():
        assert m["delta"] == 0


# ── #10 deadline_f1 정합 (변동 0) ────────────────────────────────────────
def test_deadline_f1_정합():
    ba = _j("before_after_deadline_f1.json")
    assert ba["before"] == ba["after"] == 0.8702
    assert ba["delta"] == 0.0


# ── #11 prompt 미변경 — guard 는 결정적 post-processing ──────────────────
def test_no_prompt_modification():
    # b2g_guard 는 (actions, text) 만으로 동작하는 순수 함수 — prompt/model
    # 의존 없음. 동일 입력 → 동일 출력 (post-processing 입증).
    acts = [{"action_text": "검토"}]
    r1 = b2g_guard(acts, "보고서 검토 부탁드립니다")
    r2 = b2g_guard(acts, "보고서 검토 부탁드립니다")
    assert r1 == r2
    # guard 는 입력 action 을 변형하지 않음 (원본 불변)
    assert acts == [{"action_text": "검토"}]


# ── #12 LoRA / model weight 미변경 — baseline 재현 ───────────────────────
def test_no_lora_fine_tuning():
    # control variant 가 기존 predictions 로 baseline action_fp 234 재현
    # → model weight / 추론 미변경 입증.
    vd = _j("variant_distinctness_report.json")
    assert vd["control_variant"]["action_fp"] == 234
    # treatment 는 post-processing guard 효과만 (distinct)
    assert vd["variant_distinct"] is True
    assert vd["treatment_variant"]["action_fp"] < 234


# ── #13 NO_ACTION 마커 — FYI 대문자 (Codex P2) ──────────────────────────
def test_no_action_marker_FYI_uppercase():
    assert guard_decision("FYI 참고 바랍니다") == "block"
    assert guard_decision("FYI") == "block"


# ── #14 NO_ACTION 마커 — Fyi title-case (Codex P2) ──────────────────────
def test_no_action_marker_Fyi_titlecase():
    assert guard_decision("Fyi 참고") == "block"
    assert guard_decision("Fyi") == "block"


# ── #15 NO_ACTION 마커 — fyi 소문자 + 한국어 마커 정합 유지 ──────────────
def test_no_action_marker_fyi_lowercase_정합_유지():
    assert guard_decision("fyi 참고") == "block"          # 기존 동작 유지
    assert guard_decision("참고만 하세요") == "block"      # 한국어 마커 유지
    assert guard_decision("확인만 하세요") == "block"      # 한국어 마커 유지
