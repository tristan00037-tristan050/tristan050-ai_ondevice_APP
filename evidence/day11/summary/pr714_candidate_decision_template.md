# PR #714 — Card 1 6.5.6 production candidate 공식 판정 (Template)

## Merge base
- PR #713 merge SHA: TBD
- D mode metrics file: `evidence/day11/mode_d/metrics_13.json`

## Decision input

D mode metrics 와 13지표 thresholds 비교 (algorithm team Day 11 정합 확정).

### Tier 1 — Hard Safety (PR #713 측정값 기준)
| 지표 | threshold | 측정값 | 결과 |
|---|---|---|---|
| verifier_error_auto_apply_count | = 0 | TBD | TBD |
| false_deadline_rate | ≤ 0.02 | TBD | TBD |
| no_action_fp_rate | ≤ 0.03 | TBD | TBD |
| g22_strict_warning_count | = 0 | TBD | TBD |
| g23_hard_violation_count | = 0 | TBD | TBD |

### Tier 2 — Auto-apply
| 지표 | threshold | 측정값 | 결과 |
|---|---|---|---|
| auto_apply_precision | ≥ 0.95 | TBD | TBD |
| auto_apply_recall | ≥ 0.70 | TBD | TBD |

### Tier 3 — Extraction Quality
| 지표 | threshold | 측정값 | 결과 |
|---|---|---|---|
| schema_valid_rate | ≥ 0.98 | TBD | TBD |
| normalized_action_f1 | ≥ 0.90 | TBD | TBD |
| multi_action_split_accuracy | ≥ 0.85 | TBD | TBD |
| deadline_f1 | ≥ 0.90 | TBD | TBD |

### Tier 4 — Calibration
| 지표 | threshold | 측정값 | 결과 |
|---|---|---|---|
| action_ece_after | ≤ 0.15 | TBD | TBD |
| intent_ece_after | ≤ 0.20 | TBD | TBD |

## Official Decision

verdict: TBD (PROCEED / PATCH / BLOCK)
- PROCEED: Tier 1~4 모두 threshold 통과 시 production candidate 승인
- PATCH:   Tier 2~4 1~2 항목 미달 — 영역 정정 후 재측정 진행
- BLOCK:   Tier 1 (Hard Safety) 1개 이상 실패 — production candidate 불가

## 5단 검토 (PR #714 별도)
1. 봇 코멘트 확인
2. 직접 diff 확인
3. grep 검증
4. 테스트/게이트 결과
5. 최종 판정 + 다음 단계 안내

## Day 11 → PR #714 진입 가능 조건
- PR #713 머지 완료 (MEASURED_ONLY)
- evidence/day11/mode_d/metrics_13.json 존재
- G22 strict warning_count = 0
- G23 hard violation = 0
