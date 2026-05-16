# PR #726 Algorithm Branch B-3B arbitration apply Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 725
- branch: B-3B
- patch_type: arbitration_apply
- verdict: PATCH_CONTINUE
- alignment_cycle: 1차 적용

## selected AR: AR-4

## f1 축
- normalized_action_f1: 0.6182 → 0.6182 (Δ 0.0)
- MIXED-A1 recover: 0
- MIXED-A3 recover: 0
- recovery_rate: 0.0
- action_fp: 234 (B-2 baseline 234)

## deadline 축 (Branch D 회귀 monitor)
- deadline_f1: 0.8438 (D baseline 0.8438)
- HARD↔SOFT confusion: 5
- NONE→actionable: 2

## AB simulation A/B/C
- A: 0.6829 / B: 0.6829 / C: 0.6829
- selected: B_ar2

## 1차 성공 기준: 부분 충족
## verdict: PATCH_CONTINUE