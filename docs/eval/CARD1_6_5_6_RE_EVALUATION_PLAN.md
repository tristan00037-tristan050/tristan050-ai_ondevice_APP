# Card1 6.5.6 재평가 계획 (단계 6.5.5 Day 5)

6.5.5 EvalSet 확장 완료 후 6.5.6 단계에서 모델 (Qwen3-4B v1) vs gold 평가.

## 1. 통과 기준 (모든 항목 필수)

| 항목 | 기준 |
|------|------|
| intent_type agreement (2인 라벨) | ≥ 0.85 |
| deadline_type agreement | ≥ 0.80 |
| auto_apply_allowed agreement | ≥ 0.95 |
| **모델 분류 정확도 (vs gold)** | **≥ 0.90** |
| PII leak | **0건** |
| raw_text 저장 | **0건** |
| G1~G21 통과 | **전부 ok=true** |

## 2. 평가 메트릭

| 메트릭 | 영역 |
|--------|------|
| Cohen's kappa | 2인 라벨링 합의도 |
| Precision / Recall / F1 | intent별 + deadline별 |
| Confusion matrix | intent_type 5x5 |
| Accuracy | 모델 출력 vs final_gold |
| Auto-apply precision | auto_apply=true 샘플 한정 |
| False positive rate | 위험 작업 (risky_action) 한정 |

## 3. 입력 데이터 (Day 10 확정)

- **`tests/fixtures/card1_evalset_v1_1_500.jsonl`** (500건 v1_1, 6.5.6 평가 입력)
- `tests/fixtures/card1_evalset_v1_gold.jsonl` (Day 5 gold 30건, 변경 없음)

500건 v1_1 = 4가지 mode (A/B/C/D) 의 입력.

## 3-1. 4가지 mode

| mode | 영역 | production candidate |
|------|------|----------------------|
| A | 합의도/메트릭 사전 점검 | 금지 |
| B | base 모델 평가 | 금지 |
| C | 비교 평가 (base vs ft v0) | 금지 |
| D | production candidate 판정 (정상 통과 시) | 가능 |

production candidate 판정은 **D mode 만**.

## 3-2. 13가지 핵심 지표

| # | 지표 | 영역 | 임계값 |
|---|------|------|--------|
| 1 | intent_type kappa | G5 | ≥ 0.85 |
| 2 | deadline_type kappa | G5 | ≥ 0.80 |
| 3 | auto_apply_allowed raw | G5 | ≥ 0.95 |
| 4 | 모델 분류 정확도 (vs final_gold) | B/C | ≥ 0.90 |
| 5 | confusion matrix 5x5 | B/C | 분석용 |
| 6 | auto_apply precision | C/D | ≥ 0.95 |
| 7 | 위험 작업 false positive | C/D | 0 |
| 8 | PII leak | G3 | 0 |
| 9 | raw_text 저장 | G14 | 0 |
| 10 | G1~G23 ok | 전체 | all ok=true |
| 11 | adjudication 100건 정합 | G17~G21 | ok |
| 12 | auto_apply_rate (자동 적용 비율) | D mode | 조건부 ≤ 0.20 |
| 13 | boundary precision | D mode | ≥ 0.90 (검토용) |

## 3-3. auto_apply_rate 조건부 0.20

D mode 에서 auto_apply=true 비율이 fixture 의 5.4% 보다 큰 영역(예: 20%)
까지 확장될 경우 production candidate 판정 보류. 모델이 자동 적용 후보를
과대 판정하지 않는지 검증.

## 4. 6.5.6 단계 작업 일정

| Day | 작업 |
|-----|------|
| Day 11 | 모델 평가 실행 (Qwen3-4B vs gold) |
| Day 12 | 메트릭 산출 + 결함 분석 |
| Day 13 | 5단 검토 + 판정 |
| Day 14+ | 학습 진입 또는 정정 사이클 |

## 5. 통과 조건

모든 메트릭 + 결함 0건 + 5단 형식 검토 통과 시 다음 단계 진행 검토.
미달 시 정정 사이클 진입.

## 6. 금지 사항

- raw_text 저장 금지 (Hard Gate G14)
- LoRA / 모델 변경 금지 (재평가 단계까지)
- 6.5.6 판정 이전 production 적용 금지
