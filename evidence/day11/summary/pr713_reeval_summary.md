# PR #713 — Card 1 6.5.6 Day 11 재평가 결과 요약 (MEASURED_ONLY)

## Merge base
- PR #712 merge SHA: 3b7ab991ff19f45c14aa62d65ed43f325a5e25a3
- Dataset: `tests/fixtures/card1_evalset_v1_1_500.jsonl` (500건)
- dataset_id: `card1_evalset_v1_1_500`

## 4 mode 측정 결과 (500건)

| Mode | 영역 | elapsed | schema | intent_acc(ref) | false_deadline | no_action_fp | dl_f1 | naf1 | masa | action_ece | intent_ece |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | parser only | 0.004s | 1.0 | 0.666 | 0.008 | 0.118 | 0.78 | 0.57 | — | 0.236 | 0.166 |
| B | LLM only | 1225s | 1.0 | 0.690 | 0.050 | 0.027 | 0.72 | 0.58 | 0.97 | 0.184 | 0.190 |
| C | parser+LLM | 1103s | 1.0 | 0.692 | 0.014 | 0.027 | 0.81 | 0.61 | 0.86 | 0.200 | 0.192 |
| D | C+verifier+calibrated | 1103s | 1.0 | 0.692 | 0.014 | 0.027 | 0.81 | 0.61 | 0.86 | 0.460 | 0.061 |

## D mode 13지표 4단계 비교

### Tier 1 — Hard Safety (5/5 통과)
| 지표 | threshold | 측정 | 결과 |
|---|---|---|---|
| verifier_error_auto_apply_count | = 0 | 0 | ✓ |
| false_deadline_rate | ≤ 0.02 | 0.014 | ✓ |
| no_action_fp_rate | ≤ 0.03 | 0.0273 | ✓ |
| g22_strict_warning_count | = 0 | 0 | ✓ |
| g23_hard_violation_count | = 0 | 0 | ✓ |

### Tier 2 — Auto-apply (0/2 미달)
| 지표 | threshold | 측정 | 결과 |
|---|---|---|---|
| auto_apply_precision | ≥ 0.95 | 0.0 | X |
| auto_apply_recall | ≥ 0.70 | 0.0 | X |

원인: calibrator `auto_apply_threshold` (intent 0.75 / action 0.85) 가 LLM raw confidence (0.5) 보다 높아 pred_auto=0.

### Tier 3 — Extraction Quality (2/4 미달)
| 지표 | threshold | 측정 | 결과 |
|---|---|---|---|
| schema_valid_rate | ≥ 0.98 | 1.0 | ✓ |
| normalized_action_f1 | ≥ 0.90 | 0.6065 | X |
| multi_action_split_accuracy | ≥ 0.85 | 0.8621 | ✓ |
| deadline_f1 | ≥ 0.90 | 0.8092 | X |

### Tier 4 — Calibration (1/2)
| 지표 | threshold | 측정 | 결과 |
|---|---|---|---|
| action_ece_after | ≤ 0.15 | 0.4595 | X |
| intent_ece_after | ≤ 0.20 | 0.0611 | ✓ |

## verdict
**MEASURED_ONLY** — PR #713 범위. 공식 production candidate 판정은 PR #714 에서 진행.

## Day 11 → PR #714 진행 가능 여부
- Tier 1 Hard Safety 5/5 통과 → BLOCK 아님
- Tier 2~4 일부 미달 → 공식 판정 PROCEED/PATCH 영역 (PR #714 판단 영역)
- Day 11 → PR #714 진입 **가능**

## 금지 사항 준수 확인
- LoRA 학습 없음 ✓
- 모델 교체 없음 ✓
- production candidate 문구 PR #713 미사용 ✓
- auto_apply_accuracy 단독 필드 미사용 ✓
- card1_gold_v1 dataset_id 미사용 ✓
- temperature=0.0 + seed=42 재현성 확보 ✓
