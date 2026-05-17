"""PR #731 Metric Design Review sentinel — #1~#11."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "evidence/day25/metric_design_review"

from scripts.ci.check_standard_10 import is_version_bumped  # noqa: E402
from scripts.eval.pr731_metric_design_review import (  # noqa: E402
    CONTRACT_VERSION_NEW, CONTRACT_VERSION_OLD, PRODUCTION_GATE,
    STRICT_ACTION_F1, _meta, classify_layer2,
)


def _report():
    return json.loads(
        (OUT / "mixed_a_product_equivalent_report.json").read_text(encoding="utf-8"))


# ── #1 strict_action_f1 산식 불변 ────────────────────────────────────────
def test_strict_action_f1_unchanged():
    # strict_action_f1 = 기존 normalized_action_f1 0.6182 그대로
    assert STRICT_ACTION_F1 == 0.6182
    rep = _report()
    assert rep["strict_action_f1"] == 0.6182
    # before/after — strict layer delta 0
    ba = json.loads((OUT / "before_after_comparison.json").read_text(encoding="utf-8"))
    saf = [r for r in ba["comparison"] if r["metric"] == "strict_action_f1"][0]
    assert saf["before"] == saf["after"] == 0.6182
    assert saf["delta"] == 0.0


# ── #2 manual_suggestion_precision 산식 정합 ─────────────────────────────
def test_manual_suggestion_precision_산식_정합():
    rep = _report()
    # Internal Alpha feedback 전 — 측정 미가능, null + 사유 명시 (정직 보고)
    assert rep["manual_suggestion_precision"] is None
    assert rep["manual_suggestion_precision_note"]
    assert "Alpha" in rep["manual_suggestion_precision_note"]


# ── #3 product_equivalent_action_rate 산식 정합 ──────────────────────────
def test_product_equivalent_rate_산식_정합():
    rep = _report()
    for block in (rep["full_67_classification"], rep["sample_30_classification"]):
        a3 = block["A3_product_equivalent"]
        a4 = block["A4_true_over_extraction"]
        a5 = block["A5_metric_contract_gap"]
        a6 = block["A6_unresolved_user_value"]
        denom = a3 + a4 + a5 + a6
        assert block["product_equivalent_action_rate"] == round(a3 / denom, 4)
    # 67건 전체: A3 32 / A4 29 / A5 6 / A6 0
    f = rep["full_67_classification"]
    assert (f["A3_product_equivalent"], f["A4_true_over_extraction"],
            f["A5_metric_contract_gap"], f["A6_unresolved_user_value"]) == \
        (32, 29, 6, 0)


# ── #4 dangerous_over_extraction_rate 산식 정합 ──────────────────────────
def test_dangerous_over_extraction_rate_산식_정합():
    rep = _report()
    for block in (rep["full_67_classification"], rep["sample_30_classification"]):
        a3 = block["A3_product_equivalent"]
        a4 = block["A4_true_over_extraction"]
        a5 = block["A5_metric_contract_gap"]
        a6 = block["A6_unresolved_user_value"]
        denom = a3 + a4 + a5 + a6
        assert block["dangerous_over_extraction_rate"] == round(a4 / denom, 4)


# ── #5 gold 미수정 ───────────────────────────────────────────────────────
def test_no_gold_modification():
    """a3_a4_separation_report 의 gold_intent 가 live dataset 과 일치."""
    dataset = ROOT / "tests/fixtures/card1_evalset_v1_1_500.jsonl"
    live = {}
    for line in dataset.open(encoding="utf-8"):
        if line.strip():
            it = json.loads(line)
            live[it["sample_id"]] = it["intent_type"]
    sep = json.loads((OUT / "a3_a4_separation_report.json").read_text(encoding="utf-8"))
    for c in sep["a3_product_equivalent_cases"]:
        assert c["gold_intent"] == live[c["sample_id"]]
        assert c["gold_intent"] == "QUESTION"
    for c in sep["a4_dangerous_cases"]:
        assert c["gold_intent"] == live[c["sample_id"]]
        assert c["gold_intent"] != "QUESTION"


# ── #6 threshold 변경 없음 (production gate 0.90 유지) ───────────────────
def test_no_threshold_change():
    assert PRODUCTION_GATE == 0.90
    # policy drift — strict layer 변경 없음
    drift = json.loads((OUT / "policy_drift_report.json").read_text(encoding="utf-8"))
    assert drift["drift_rate"] == 0.0
    assert drift["drift_class"] == "OK"


# ── #7 metric contract version bump (SemVer v1.0.0 → v2.0.0) ─────────────
def test_metric_contract_version_bump():
    assert CONTRACT_VERSION_OLD == "1.0.0"
    assert CONTRACT_VERSION_NEW == "2.0.0"
    assert is_version_bumped(CONTRACT_VERSION_OLD, CONTRACT_VERSION_NEW)
    drift = json.loads((OUT / "policy_drift_report.json").read_text(encoding="utf-8"))
    assert drift["old_policy_version"] == "1.0.0"
    assert drift["new_policy_version"] == "2.0.0"


# ── #8 Layer 1/2 분리 원칙 — Layer 2 로 production gate 통과 불가 ─────────
def test_layer_1_2_분리_원칙():
    rep = _report()
    # Layer 1 strict_action_f1 만이 production gate — 현재 미달
    assert rep["strict_action_f1"] < PRODUCTION_GATE
    # Layer 2 연구용 지표는 production 의사결정 불가 — null
    assert rep["suggestion_value_adjusted_f1"] is None
    assert "production 사용 금지" in rep["suggestion_value_adjusted_f1_note"]
    # classify_layer2 결정적 — gold>=1 은 A5 (Layer 2 분리)
    a5 = classify_layer2({"gold_action_count": 1, "pred_action_count": 1,
                          "gold_intent": "QUESTION"})
    assert a5 == "A5_metric_contract_gap"
    a3 = classify_layer2({"gold_action_count": 0, "pred_action_count": 1,
                          "gold_intent": "QUESTION"})
    assert a3 == "A3_product_equivalent_prediction"
    a4 = classify_layer2({"gold_action_count": 0, "pred_action_count": 1,
                          "gold_intent": "REPORT"})
    assert a4 == "A4_true_over_extraction_error"


# ── #9 A5 는 gold>=1 AND pred>=1 (Codex P1) ──────────────────────────────
def test_A5_requires_gold_and_pred():
    assert classify_layer2({"gold_action_count": 2, "pred_action_count": 2,
                            "gold_intent": "REPORT"}) == "A5_metric_contract_gap"
    assert classify_layer2({"gold_action_count": 1, "pred_action_count": 1,
                            "gold_intent": "QUESTION"}) == "A5_metric_contract_gap"


# ── #10 A5 는 gold-only (pred=0) 케이스 제외 → A7 (Codex P1) ─────────────
def test_A5_excludes_gold_only():
    result = classify_layer2({"gold_action_count": 2, "pred_action_count": 0,
                              "gold_intent": "REPORT"})
    assert result != "A5_metric_contract_gap"
    assert result == "A7_false_negative"
    # gold=0/pred=0 은 MIXED-A 영역 아님
    assert classify_layer2({"gold_action_count": 0, "pred_action_count": 0,
                            "gold_intent": "QUESTION"}) == "no_action"


# ── #11 evidence metadata deterministic (Codex P2) ───────────────────────
def test_evidence_metadata_deterministic():
    meta1 = _meta()
    meta2 = _meta()
    assert meta1 == meta2, "동일 입력 _meta() 가 비결정적"
    # wall-clock generated_at 의존 금지 — 제거됨
    assert "generated_at" not in meta1
    # tracked evidence 파일에도 generated_at 부재
    rep = _report()
    assert "generated_at" not in rep
