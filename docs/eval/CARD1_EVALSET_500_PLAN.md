# Card1 EvalSet 500건 확장 계획 (단계 6.5.5 Day 5)

## 1. 현재 상태 (Day 5 종료 시점)

| label_status | 건수 | 비고 |
|--------------|-----:|------|
| gold_v1 | 30 | adjudication 완료, reviewer 부여 |
| gold_reviewed | 110 | Day 2~3 synthetic_gold |
| draft | 60 | userlog_redacted (라벨 미부여) |
| **합계** | **200** | |

## 2. 500건 목표 분포 (±5% 허용 오차)

| 유형 | 목표 | 비율 |
|------|-----:|-----:|
| REQUEST | 150 | 30% |
| QUESTION | 75 | 15% |
| REPORT | 100 | 20% |
| COMMAND | 75 | 15% |
| NO_ACTION | 50 | 10% |
| 복합 다중 (slice_tag) | 25 | 5% |
| boundary (slice_tag) | 25 | 5% |

## 3. 300건 신규 추가

- synthetic_gold 180건 (라벨 가이드 §8 예시 확장)
- userlog_redacted 120건 (베타/내부 로그 익명화)
- 신규 300건 중 100건은 double_labeled 거쳐 adjudication

## 4. 2인 라벨링 필요 비율

- 신규 300건 중 약 **33%** (100건) 을 double_labeled.
- 의도된 불일치 + 우연 불일치 약 5~10% 예상 → adjudication 5~10건.

## 5. auto_apply_allowed=true 샘플 권장 비율

- 현재: 1/200 (0.5%) — 6.5.6 재평가 시 통계적 신뢰성 부족 가능.
- **권장: 10~15건 (5~7%)** — 알고리즘 팀 결정 필요.
- 모든 auto_apply=true 샘플은 auto_apply_reasoning + final_gold 완비 (G20/G21).

## 6. draft 60건 처리 옵션 (알고리즘 팀 결정 요청)

| 옵션 | 영역 | 비고 |
|------|------|------|
| A | 60건 모두 gold_v1 후보 | 추가 라벨링 + adjudication |
| B | 일부만 (예: 30건) | 우선순위 기준 명확화 |
| C | 전부 별도 | 500건 확장 안에 흡수 |

## 7. 일정 (Day 6~10 예상)

| Day | 작업 |
|-----|------|
| 6 | synthetic_gold 80건 추가 + Gate 검증 |
| 7 | userlog_redacted 60건 anonymize + draft 부여 |
| 8 | double_labeled 50건 + agreement 측정 |
| 9 | adjudication + gold_v1 전환 |
| 10 | 500건 최종 패키징 + 500건 fixture 분리 |

## 8. Gate 적용

모든 신규 데이터는 G1~G21 통과 필수. 위반 시 fail-closed.
