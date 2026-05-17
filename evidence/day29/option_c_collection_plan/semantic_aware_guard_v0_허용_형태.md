# Semantic-aware Guard v0 허용 형태 (자문 6차 §5)

## metadata
- source_pr: 735
- branch: Option-C-Collection-Plan
- verdict: MEASURED_ONLY

## 배경

PR #732 B-2G 는 text-only post-processing guard 로, 잔여 A4 9건('부탁
드립니다' 형 / '보고드리려고 합니다' 형)을 안전 차단하지 못했다 (실제
요청 / A5 와 표면 동일). 자문 6차 §5 는 semantic-aware guard v0 의
**허용 형태**를 정량 정의했다.

## 허용 형태 (자문 6차 §5)

| 형태 | 설명 |
|---|---|
| post-hoc policy | Internal Alpha feedback 기반 사후 정책 — 추론 후 단계 |
| warning badge | manual review 단계에서 high-risk suggestion 에 "검토 필요" 표시 |
| low_confidence marking | 차단이 아니라 우선순위 조정 — 낮은 confidence 표시 |

핵심: guard 는 **차단(block)** 이 아니라 **표시(mark)** 중심. 사용자가
manual review 단계에서 위험을 인지하도록 보조한다 (auto_apply OFF 유지).

## 절대 금지 (자문 6차 §5/§12)

- prompt recall 강화 (Branch B-2R) — 금지.
- LoRA / fine-tuning — 금지.
- 모델 교체 (Branch F) — 금지.
- 자동 실행 gate 완화 (auto_apply ON) — 금지.
- text-only guard 추가 강화 (자문 6차 M-1) — 금지.

## 본 PR 범위

본 PR 은 semantic-aware guard v0 의 허용 형태를 **정의만** 한다. 실제
구현은 별도 PR 이며, Internal Alpha feedback (option C) 수집 후 post-hoc
policy 의 데이터 기반으로 진행한다.
