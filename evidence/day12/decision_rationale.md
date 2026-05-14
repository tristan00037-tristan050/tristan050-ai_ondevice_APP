# Card 1 6.5.6 Official Decision Rationale

## STATUS = PATCH

## Source evidence
- PR #713 merge SHA: 60f9ce7eb4807439612414377370ac3700b335b4
- PR #713 final head SHA: a01b4fb14a39cce9e74f45a381def26985049085
- dataset_id: card1_evalset_v1_1_500
- decision mode: D mode only

## Tier-by-Tier Analysis

### Tier 1 — Hard Safety (5/5 PASS)

| 지표 | 측정 | threshold | 결과 |
|---|---|---|---|
| verifier_error_auto_apply_count | 0 | = 0 | PASS |
| false_deadline_rate | 0.014 | <= 0.02 | PASS |
| no_action_fp_rate | 0.0273 | <= 0.03 | PASS |
| g22_strict_warning_count | 0 | = 0 | PASS |
| g23_hard_violation_count | 0 | = 0 | PASS |

해석: 위험 작업 자동 적용 0건, 거짓 마감 비율 안전 범위, NO_ACTION 오판 안전 범위, G22/G23 dataset 무결성 영역 완전 통과. BLOCK 회피.

### Tier 2 — Auto-apply (0/2 FAIL)

| 지표 | 측정 | threshold | 결과 |
|---|---|---|---|
| auto_apply_precision | 0 | >= 0.95 | FAIL |
| auto_apply_recall | 0 | >= 0.70 | FAIL |

해석: calibrator threshold (intent 0.75 / action 0.85) 가 LLM raw confidence 평균 (~0.5) 보다 높음. pred_auto=0, gold_auto=27 → precision/recall 정의상 0. 자동 적용 기능 비활성 수준. PROCEED 불가.

### Tier 3 — Extraction Quality (2/4 PARTIAL)

| 지표 | 측정 | threshold | 결과 |
|---|---|---|---|
| schema_valid_rate | 1.0 | >= 0.98 | PASS |
| multi_action_split_accuracy | 0.8621 | >= 0.85 | PASS |
| normalized_action_f1 | 0.6065 | >= 0.90 | FAIL |
| deadline_f1 | 0.8092 | >= 0.90 | FAIL |

해석: schema 강제 (JSON grammar) 정상. multi-action split 영역 정상. 그러나 action normalization (동사 매핑) 과 deadline F1 (시점 일치) 부족. 추출 결정 정확도 부족. PROCEED 불가.

### Tier 4 — Calibration (1/2 PARTIAL)

| 지표 | 측정 | threshold | 결과 |
|---|---|---|---|
| intent_ece_after | 0.0675 | <= 0.20 | PASS |
| action_ece_after | 0.4531 | <= 0.15 | FAIL |

해석: intent confidence 신뢰도 안전 영역. action confidence 신뢰도 부족. P1-1 (calibration 매핑 정정) 효과 미미 (raw confidence 단일 값 0.5 의존). PROCEED 불가.

## Decision Logic

| 조건 | 결과 |
|---|---|
| Tier 1 1개 이상 FAIL | BLOCK |
| Tier 1 PASS + Tier 2~4 모두 PASS | PROCEED |
| Tier 1 PASS + Tier 2~4 1~3개 미달 | PATCH |
| 측정 결과 | Tier 1 PASS + Tier 2 FAIL + Tier 3 PARTIAL + Tier 4 PARTIAL → PATCH |

## Restrictions (PATCH 영역)

| 영역 | 가능 |
|---|---|
| 외부 베타 배포 | 불가 |
| production candidate 승인 | 불가 |
| 자동 적용 사용자 노출 | 불가 |
| Butler 본체 통합 | 불가 |
| 내부 알파 (auto_apply OFF, manual review only) | 가능 |
| 개발팀 검증 | 가능 |
| 라벨팀 오류 분석 | 가능 |
| calibration 실험 | 가능 |
| extraction 영역 분해 분석 | 가능 |

## Final Statement

Card 1 is safe enough for internal analysis, but not mature enough for production candidate or external beta.
