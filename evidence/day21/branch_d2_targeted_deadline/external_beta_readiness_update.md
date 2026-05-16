# External Beta Readiness Update (PR #727 Branch D-2)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 726
- branch: D-2
- verdict: PATCH_CONTINUE

- normalized_action_f1: 0.6182 (기준 0.75)
- deadline_f1: 0.8702 (기준 0.86 — 충족)
- false_deadline_rate: 0.014 (safety gate ≤ 0.02 — 충족; computed_from_d2_actionable=true)

## Codex P1 정정 — safety metric measurement integrity
- false_deadline_rate 는 D-2 mode 의 patched_actionable 기준으로 산출
- safety gate 판정 신뢰도 정량 보증 (pre-patch 필드 오용 제거)
- deadline_f1 0.8702 정합 유지 (D-2 mode 측정 — 정정 영향은 산식만)

외부 베타 진입은 두 기준 모두 충족 시 별도 판정 PR 영역.