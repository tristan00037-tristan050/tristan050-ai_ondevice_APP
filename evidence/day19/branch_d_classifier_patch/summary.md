# PR #724 Algorithm Branch D classifier patch Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 723
- branch: D
- patch_type: deadline_classifier
- verdict: MEASURED_ONLY
- alignment_cycle: 1차 측정

## deadline 축 (Branch D)
- deadline_f1: 0.8092 → 0.8438 (Δ 0.0346)
- relative_time_mismatch_rate: 0.2442 → 0.186
- HARD↔SOFT confusion: 14 → 5
- NONE→actionable: 6 → 2
- INQUIRY/URGENCY/CONDITION 보존: 28/38

## action 축 (Branch B-2 회귀 monitor)
- normalized_action_f1: 0.6182
- action_fp: 234 (B-2 baseline 234)
- action_fn: 13

## AB simulation A/B/C
- A: 0.6667
- B (D-1+D-3+D-4): 0.7826
- C (B+D-2): 0.7826
- selected: B_d1_d3_d4

## AB composition (sentinel #7)
- composition_ok: True / fail_class: AB_COMPOSITION_NATURAL_SHORTAGE

## 1차 성공 기준: 부분 충족
## verdict: PATCH_CONTINUE