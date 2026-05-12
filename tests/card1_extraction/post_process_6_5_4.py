"""6.5.4 post-process — fitted Platt(A,B)를 per-sample 에 재적용해서
auto_apply_rate / auto_apply_accuracy를 재계산.

eval 스크립트는 default Platt(A=-4, B=2)로 component conf를 만들기 때문에
fitted A/B의 효과가 auto_apply 결정에 반영되지 않음. 이 스크립트가 보정.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RESULT = ROOT / "tests" / "card1_extraction" / "step_6_5_4_full_result.json"

from butler_pc_core.card1_extraction.action_normalizer import normalize_action_verb
from butler_pc_core.card1_extraction.confidence import (
    AUTO_APPLY_THRESHOLDS, COMPONENT_WEIGHTS,
    weighted_final_confidence, should_auto_apply,
)


def sigmoid(raw, a, b):
    z = a * raw + b
    if z > 35: return 1e-12
    if z < -35: return 1.0 - 1e-12
    return 1.0 / (1.0 + math.exp(z))


def _norm_set(actions):
    return {normalize_action_verb(a) for a in actions if a} - {"other"}


def main() -> int:
    if not RESULT.exists():
        print(f"[FATAL] {RESULT} 미존재", file=sys.stderr); return 2

    data = json.loads(RESULT.read_text(encoding="utf-8"))
    cal  = data["calibration"]
    a_A, a_B = cal["action_A"],   cal["action_B"]
    i_A, i_B = cal["intent_A"],   cal["intent_B"]

    print(f"[Fitted Platt] action(A={a_A}, B={a_B})  intent(A={i_A}, B={i_B})")

    auto_apply_count = 0
    auto_apply_correct = 0
    auto_apply_reason_counter = {}
    final_weighted_dist = []

    for rec in data["per_sample"]:
        d = rec["D"]
        # fitted component conf
        fitted_action_conf = round(sigmoid(d["action_raw"], a_A, a_B), 4)
        fitted_intent_conf = round(sigmoid(d["intent_raw"], i_A, i_B), 4)
        deadline_conf      = d["deadline_conf"]
        material_conf      = d["material_conf"]

        components = {
            "action":   fitted_action_conf,
            "intent":   fitted_intent_conf,
            "deadline": deadline_conf,
            "material": material_conf,
        }
        present = set(d["present_fields"])

        # hard gate
        gates = {
            "schema_ok":   d["schema_valid"],
            "verifier_ok": all(e not in ("block_1_no_evidence_deadline",
                                         "block_2_no_evidence_material",
                                         "block_3_no_evidence_action_evidence",
                                         "block_4_negated_action",
                                         "block_7_false_deadline_no_evidence")
                               for e in d["verifier_errors"]),
            "evidence_ok": True,  # all actions have source evidence (assumed in eval)
        }

        final_w = weighted_final_confidence(components, present, gates)
        ok, reason = should_auto_apply(components, present, final_w, gates)

        rec["D_post"] = {
            "fitted_action_conf": fitted_action_conf,
            "fitted_intent_conf": fitted_intent_conf,
            "final_weighted":     final_w,
            "auto_apply_ok":      ok,
            "auto_apply_reason":  reason,
            "gates":              gates,
        }

        final_weighted_dist.append(final_w)
        if ok:
            auto_apply_count += 1
            # correctness check
            gold_intent  = rec["expected"]["intent_type"].lower()
            gold_actions = [a["action_text"] for a in rec["expected"]["actions"]]
            pred_intent  = d["intent"]
            pred_actions = d["actions"]
            intent_ok    = (pred_intent == gold_intent)
            gn = _norm_set(gold_actions); pn = _norm_set(pred_actions)
            action_norm_ok = (pn == gn) or (gn.issubset(pn) if gn else not pn)
            if intent_ok and action_norm_ok:
                auto_apply_correct += 1
        auto_apply_reason_counter[reason] = auto_apply_reason_counter.get(reason, 0) + 1

    total = data["total_items"]
    aa_rate = round(auto_apply_count / total, 4)
    aa_acc  = round(auto_apply_correct / auto_apply_count, 4) if auto_apply_count else None

    print(f"\n[Post-fit Auto Apply]")
    print(f"- auto_apply_count: {auto_apply_count}/{total}  rate={aa_rate}")
    print(f"- auto_apply_correct: {auto_apply_correct}")
    print(f"- auto_apply_accuracy: {aa_acc}")
    print(f"\n[Auto-apply reasons]")
    for r, c in sorted(auto_apply_reason_counter.items(), key=lambda x: -x[1]):
        print(f"  {r}: {c}")

    # final_weighted 분포
    fw_sorted = sorted(final_weighted_dist, reverse=True)
    print(f"\n[final_weighted 분포]")
    print(f"  max:   {fw_sorted[0]:.4f}")
    print(f"  ≥0.80: {sum(1 for v in fw_sorted if v >= 0.80)}건")
    print(f"  ≥0.70: {sum(1 for v in fw_sorted if v >= 0.70)}건")
    print(f"  ≥0.50: {sum(1 for v in fw_sorted if v >= 0.50)}건")
    print(f"  median: {fw_sorted[len(fw_sorted)//2]:.4f}")
    print(f"  min:   {fw_sorted[-1]:.4f}")

    # 결과 갱신
    data["post_fit_auto_apply"] = {
        "auto_apply_rate":           aa_rate,
        "auto_apply_accuracy":       aa_acc,
        "auto_apply_count":          auto_apply_count,
        "auto_apply_correct":        auto_apply_correct,
        "auto_apply_reasons":        auto_apply_reason_counter,
        "final_weighted_max":        round(fw_sorted[0], 4),
        "final_weighted_p50":        round(fw_sorted[len(fw_sorted)//2], 4),
        "final_weighted_above_80":   sum(1 for v in fw_sorted if v >= 0.80),
        "final_weighted_above_70":   sum(1 for v in fw_sorted if v >= 0.70),
    }
    RESULT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[Save] {RESULT.relative_to(ROOT)}  (augmented with post-fit auto-apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
