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

## Day 7 strict mode 추가 (알고리즘 팀 옵션 2 확정)

### 두 가지 동작 모드

| 모드 | 동작 | 사용 시점 |
|------|------|----------|
| 기본 (warning-only) | warning 기록, ok=true | Day 7~9 관측 |
| strict (--fail-on-warning) | warning > 0 시 fail-closed | Day 10 / 6.5.6 / release / training handoff |

### strict mode 필수 적용 시점 (알고리즘 팀 확정)

| # | 시점 |
|---|------|
| 1 | Day 10 최종 EvalSet 패키징 |
| 2 | 6.5.6 production candidate 판정 |
| 3 | gold_v1 최종 패키징 |
| 4 | 모델 학습 또는 relabeling handoff |
| 5 | release branch 생성 |

### 사용법

```bash
# CLI
python3 scripts/evalset/check_duplicate_label_consistency.py \
  --input ... --fail-on-warning --out ...

# 환경변수
EVALSET_FAIL_ON_WARNING=1 \
python3 scripts/evalset/check_duplicate_label_consistency.py \
  --input ... --out ...
```

우선순위: **CLI > 환경변수 > 기본값(False)**

### fail_class

`DUPLICATE_WARNING_FIELD_INCONSISTENCY` (action_required / answer_required 통합)

### Day 7~9 통계 수집 계획

| Day | 산출물 |
|-----|--------|
| Day 7 | `evidence/evalset/day7/g22_warning_report.json` (baseline) + `g22_strict_report.json` |
| Day 8 | `evidence/evalset/day8/g22_warning_report.json` (2인 라벨링 후 재측정) |
| Day 9 | `evidence/evalset/day9/g22_warning_report.json` (adjudication 후) |
| Day 10 | `evidence/evalset/day10/g22_strict_report.json` (최종 패키징 strict) |

### hard 승격 검토 기준 (Day 8/9)

- 같은 raw_digest16 그룹에서 2회 이상 반복 충돌 → hard field 승격 검토
- Day 9 adjudication 이후에도 warning_count > 0 잔존 → 승격 검토
- 6.5.6 평가 지표 영향 확인 후 최종 결정

### Day 10 최종 패키징 기준

**warning_count = 0 필수**. 1건이라도 남으면 6.5.6 진입 보류.

### 회귀 테스트 (Day 7 strict 3건 추가)

- `test_g22_warning_only_default_passes` — 기본 모드 warning-only PASS
- `test_g22_fail_on_warning_blocks_via_cli_flag` — CLI 플래그로 fail-closed
- `test_g22_fail_on_warning_blocks_via_env_var` — 환경변수로 fail-closed
