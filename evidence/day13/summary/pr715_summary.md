# PR #715 — Calibration + Auto-apply Threshold Rework Summary

## verdict
MEASURED_ONLY (PR #715 범위, PROCEED 판정 절대 금지 — PR #718 영역)

## Source
- PR #714 merge SHA: 1632c0c7c421e3d814fa935ff542c570bd72c41c
- PR #713 merge SHA: 60f9ce7eb4807439612414377370ac3700b335b4
- dataset_id: card1_evalset_v1_1_500

## Split (Hard Gate)
- fit:     150
- holdout: 350
- seed:    42
- fit auto_apply true:     8
- holdout auto_apply true: 19
- disjoint: True

## Selected variant
- name: A_frozen_baseline
- intent_threshold: 0.75
- action_threshold: 0.85

## Tier 1~4 (holdout 350)
- Tier 1 Hard Safety: verifier_err=0 / fd=0.0171 / na_fp=0.0163 / g22=0 / g23=0
- Tier 2 Auto-apply:  precision=0.0812 / recall=1.0
- Tier 3 Extraction:  schema=1.0 / masa=0.9048 / naf1=0.6038 / dl_f1=0.8211
- Tier 4 Calibration: action_ece=0.5186 / intent_ece=0.2548
