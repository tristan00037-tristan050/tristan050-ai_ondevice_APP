# D-2 Targeted Deadline Patch Design (자문 4차 1순위)

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 726
- branch: D-2
- patch_type: targeted_deadline_normalization
- verdict: PATCH_CONTINUE

## D2-A HARD 강제
- 내일까지 / 오늘까지 / 모레까지 / 요일+까지 / 명시 날짜 / 명시 시각+까지 / 전까지
## D2-B SOFT
- 오늘 중 / 내일 중 / 이번 주 안에 / 이번 주 중 / 다음 주 안에 / 가능하면 / 조만간
## D2-C INQUIRY (non-actionable)
- 언제까지 / 기한이 어떻게 / 마감이 언제 / 언제인가요
## D2-D CONDITION (non-actionable)
- 완료되면 / 확인되면 / 정리되면 / 수정이 끝나면 / 끝나면
## D2-E URGENCY (non-actionable)
- 바로 / 즉시 / 긴급 / 가능한 빨리 / 지금 바로

## 우선순위
non-actionable (D2-C/D/E) > D2-A HARD > D2-B SOFT

## 금지 (자문 4 명시)
- 전체 deadline classifier 재작성 금지
- URGENCY/CONDITION 을 actionable 로 흡수 금지