# Branch B-3B Readiness (PR #725 측정 결과 기준)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 723
- branch: B-3A
- verdict: MEASURED_ONLY

## arbitration rule 후보 5개 (AR-1~AR-5)
- MIXED-A 67건 6 subtype 분류 완료
- total_estimated_recoverable: 37.3

## Branch B-3B 진입 조건
- arbitration rule 중 safety regression 시뮬 0 인 rule 만 적용 대상
- AR-1 (evidence-aware) / AR-3 (conservative-wins) 우선 후보
- AR-2 (hybrid merge) 는 action_fp 회귀 모니터 필수
- AR-5 (hold) 는 적용 없음

## 적용 금지 (PR #725 측정 PR 성격)
Branch B-3B 별도 PR 에서 arbitration rule 실제 적용 + AB simulation.