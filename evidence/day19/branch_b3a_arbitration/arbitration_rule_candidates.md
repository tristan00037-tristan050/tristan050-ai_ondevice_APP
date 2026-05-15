# Arbitration Rule Candidates (Branch B-3A, 측정 only)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 723
- branch: B-3A
- patch_type: arbitration_measurement_only
- verdict: MEASURED_ONLY

## 후보 (적용 금지 — Branch B-3B 별도 PR)

### AR-1 evidence-aware arbitration (MIXED-A3 대상)
- parser 가 evidence 일치 + LLM 이 action 추출 → parser evidence 채택

### AR-2 hybrid merge rule (MIXED-A1 대상)
- parser action + LLM object 병합 (intent 는 LLM)

### AR-3 conservative-wins (MIXED-A4/A5 대상)
- over-extraction 측에서 conservative 쪽 채택 (Branch B-2 over_guard 정합)

### AR-4 deadline delegation (MIXED-A2 대상)
- deadline 영역은 Branch D classifier 결과로 위임

### AR-5 hold-and-accumulate (MIXED-A6 대상)
- no clear winner — 현 단계 보류, evidence 축적만

## 적용 정책
PR #725 는 측정 PR. arbitration rule 적용 자체는 Branch B-3B 별도 PR.