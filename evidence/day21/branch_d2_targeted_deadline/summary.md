# PR #727 Algorithm Branch D-2 targeted deadline Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 726
- branch: D-2
- patch_type: targeted_deadline_normalization
- verdict: PATCH_CONTINUE
- alignment_cycle: 1차 측정 + Codex P1 정정 (false_deadline actionable 기준)

## Codex P1 정정 (safety metric measurement integrity)
- measure_deadline() false_deadline 산식을 mode 별 actionable 기준으로 분리
- baseline_d1: pre-patch deadline_is_actionable / d2_targeted: d2_classify patched_actionable
- false_deadline_rate: baseline 0.014 → d2_targeted 0.014 (count 7 → 7)
- computed_from_d2_actionable: true (D-2 보정 actionable 반영)

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