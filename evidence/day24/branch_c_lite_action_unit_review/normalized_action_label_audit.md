# normalized_action Label Audit (분석 전용 — 수정 금지)

## metadata
- source_pr: 730
- branch: C-lite
- verdict: MEASURED_ONLY

## label_too_narrow 케이스
- 30건 중 pred action 이 canonical label 에 매핑되지 않은 (other) 케이스: 7건
  - card1_100031
  - card1_100048
  - card1_100101
  - card1_200051
  - card1_400061
  - card1_400063
  - card1_400065

## 분석 (실제 수정 금지 — 자문 4 명시)
- label 추가/통합/제거 후보는 본 PR 에서 변경하지 않는다.
- MIXED-A 의 본질이 label 협소함보다 over-extraction (gold=0/pred>=1) 에 있으므로, label set 확장은 우선순위가 낮다.