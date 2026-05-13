# G22 v2 — action_required / answer_required 승격 검토 (Day 7)

## 알고리즘 팀 자문 결과 (2026-05-14)

**결정:** warning 추가, hard 승격 보류.
- `action_required` / `answer_required` 는 의미상 같은 raw 라도 컨텍스트에 따라
  다르게 라벨링될 여지가 있음 (예: 같은 발화가 보고/요청 양립 가능).
- 즉시 hard fail 처리 시 over-blocking 위험.
- Day 8/9 에서 충돌 통계 (warning_count) 수집 후 hard 승격 검토.

## v2 구조

| 항목 | 값 |
|------|------|
| HARD_FIELDS | `intent_type` / `deadline_type` / `auto_apply_allowed` (변경 없음) |
| **WARNING_FIELDS (신규)** | `action_required` / `answer_required` |
| 충돌 처리 | warnings 배열에 누적, ok=true 유지 |
| fail_class 후보 (준비만) | `DUPLICATE_ACTION_REQUIRED_INCONSISTENCY` / `DUPLICATE_ANSWER_REQUIRED_INCONSISTENCY` |

## Day 8/9 검토 계획

| Day | 작업 |
|-----|------|
| Day 8 | warning_count 통계 + 2인 라벨링 진행 |
| Day 9 | warning_count ≥ 임계값 + 정합성 영향 분석 |
| Day 10 | hard 승격 또는 보류 최종 결정 |

## hard 승격 조건 후보

- warning_count / duplicate_groups ≤ 5% — 보류 (현 결정)
- 5% < ratio ≤ 15% — 사례 분석 후 결정
- ratio > 15% — over-blocking 위험으로 추가 분석

## 회귀 테스트

`tests/evalset/test_duplicate_label_consistency.py` 에 3건 추가:
- `test_g22_v2_warning_on_action_required_mismatch`
- `test_g22_v2_warning_on_answer_required_mismatch`
- `test_g22_v2_warning_does_not_fail_when_hard_fields_ok`
