# Post-Decision PR Plan (PR #714 PATCH 후속)

## PR #715 — Calibration + Auto-apply Threshold Rework

### 영역
- calibration split: fit 150 / holdout 350 (overfit 차단)
- threshold sweep:
  - intent 0.50 ~ 0.85 / step 0.05
  - action 0.50 ~ 0.90 / step 0.05
- precision-first 영역 (auto_apply_precision >= 0.95 우선 만족)
- holdout 평가 (fit set 와 분리)
- 500건 전체 fit + 같은 세트 판정 **금지** (data leakage 차단)

### 진입 조건
- PR #714 머지 완료
- evidence/day12/ 영역 확정

### 산출 영역
- evidence/day13/calibration_sweep.json
- evidence/day13/holdout_eval_metrics.json
- evidence/day13/auto_apply_threshold_decision.md

## PR #716 — Extraction Error Decomposition

### 영역
- normalized_action_f1 0.6065 원인 분해
- deadline_f1 0.8092 원인 분해
- action FN/FP top pattern
- parser vs LLM disagreement
- normalized_action mapping gap (predicted 동사 → normalized_action enum)

### 진입 조건
- PR #714 머지 완료

### 산출 영역
- evidence/day14/action_error_breakdown.json
- evidence/day14/deadline_error_breakdown.json
- evidence/day14/parser_llm_disagreement.json

## PR #717 — Conditional LoRA only if required

### 영역
- 바로 LoRA 학습 **금지**
- mapping / prompt / schema / verifier 보완 후에도 부족할 때만
- 진입 조건: PR #715 + PR #716 결과 분석 후 알고리즘 팀 결정

### 산출 영역 (필요 시)
- evidence/day15/lora_training_decision.md
- evidence/day15/lora_eval_metrics.json

## PR #718 — Final D mode re-measurement

### 영역
- PR #715/#716/#717 결과 반영 후
- D mode 13지표 재평가 (500건)
- Butler 본체 통합 진입 조건 확인
- official verdict PROCEED / PATCH / BLOCK 재판정

### 진입 조건
- PR #715 완료
- PR #716 완료
- PR #717 완료 (필요 시)

### 산출 영역
- evidence/day16/mode_d/metrics_13.json
- evidence/day16/mode_d/production_candidate_inputs.json
- evidence/day16/summary/pr718_final_decision.md

## Butler Main Integration 진입 조건 (전체)

1. PR #715 ✅
2. PR #716 ✅
3. PR #717 (필요 시) ✅
4. PR #718 D mode final re-measurement ✅
5. PR #718 결과 Tier 1~4 모두 PASS ✅
6. PR #718 official verdict = PROCEED ✅
