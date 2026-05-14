# Butler Main Integration Handoff (Card 1 6.5.6)

## STATUS = PATCH → Butler 본체 통합 차단

## Butler Main Integration 진입 조건 (6가지)

Butler 본체 통합은 **다음 모든 조건 충족 시에만** 진행:

1. PR #715 완료 — Calibration + Auto-apply Threshold Rework
2. PR #716 완료 — Extraction Error Decomposition
3. PR #717 완료 (필요 시) — Conditional LoRA only if required after #715/#716
4. PR #718 완료 — Final D mode re-measurement
5. PR #718 결과 Tier 1~4 모두 PASS
6. PR #718 official verdict = PROCEED

## 진입 조건 미충족 시 금지 영역

- Butler 본체 통합 PR 선착수 금지
- 카드 1 외부 베타 배포 금지
- 자동 적용 사용자 노출 금지
- production candidate 승인 금지

## 알고리즘 팀 / 메인 팀 통합 정합

- D mode only 가 공식 판정 영역
- A/B/C mode 는 비교/분석 영역 (공식 판정 영역 아님)
- 후속 PR #715/#716/#717/#718 결과 PR #718 단일 D mode 재측정으로 통합
