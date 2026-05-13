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

## 3. 입력 데이터

- gold v1.0 30건 (현재) 또는
- 500건 확장 후 gold (Day 10 이후)

알고리즘 팀 결정 영역.

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
