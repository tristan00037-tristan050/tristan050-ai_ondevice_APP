# PR #727 Algorithm Branch D-2 targeted deadline Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 726
- branch: D-2
- patch_type: targeted_deadline_normalization
- verdict: PATCH_CONTINUE
- alignment_cycle: 1차 측정

## deadline 축
- deadline_f1: 0.8438 → 0.8702 (Δ 0.0264)
- relative_time_mismatch_rate: 0.1868 → 0.1538
- HARD↔SOFT confusion: 5 → 5
- NONE→actionable: 2 → 2
- INQUIRY/URGENCY/CONDITION 보존: 28/38

## action 축 (Branch B-2 회귀 monitor)
- normalized_action_f1: 0.6182
- action_fp: 234 (B-2 baseline 234)

## AB simulation A/B/C
- A: 0.4545 / B: 0.6957 / C: 0.7234
- selected: C_d1_d2

## 1차 성공 기준: 부분 충족
## verdict: PATCH_CONTINUE