# Standard 9 — Dataset Integrity Fail-Closed

Status: active from the next evaluation PR after PR #728
Scope: `scripts/eval/*`, `tests/eval/*`, `evidence/day*/`, evaluation PR descriptions
Codified by: GitHub PR #728 (Algorithm Branch 영역 변경 없음 — 정착 PR)
CI guard: `scripts/ci/check_standard_09.py`
Sentinel: `tests/standards/test_standard_09_dataset_integrity.py`

## Purpose

평가 결과(F1, precision, recall, ECE, deadline rate 등)는 dataset 정합성이
보장될 때만 의미를 가진다. Standard 6 (Coverage fail-closed sentinel) 이
PR #718 / #722 / #723 / #725 / #726 의 5회 회귀에 걸쳐 dataset-level
integrity 결함을 반복적으로 차단한 사실이 입증되었다. 자문 4차 8 은 mixed
unit 및 action unit 의 dataset-level integrity 가 결정적이라고 명시했다.

이에 Standard 6 의 coverage fail-closed 검사를 단일 표준 Standard 9 로
승격하고, duplicate label drift / semantic label violation / action unit
mismatch / gold granularity mismatch / evidence-source mismatch / D-2 mode
actionable 산식까지 dataset integrity 의 범위로 통합한다.

## Verified source incidents (5회 회귀 입증)

- PR #718: head drift 와 coverage fail-closed sentinel 최초 입증.
- PR #722: AB composition fail-closed + gold duplicate 탐지 (coverage 6→10 필드).
- PR #723: `GOLD_SAMPLE_ID_DUPLICATE` fail_class + BEHIND state 진단.
- PR #725: evidence/source mismatch — MIXED-A avg_evidence_score 정합 진단.
- PR #726: prediction coverage drift fail-closed (coverage 10→12 필드).
- PR #727: `measure_deadline()` baseline/patched mode 분리 산식 정정 (Codex P1).

## coverage_report 12 필드 명세

모든 평가 PR 의 evidence 에는 `coverage_report.json` 이 포함되어야 하며,
다음 12 필드를 모두 가져야 한다.

| 필드 | 타입 | 의미 |
|---|---|---|
| `coverage_checked` | bool | coverage 검사 실행 여부 (항상 true) |
| `expected_samples` | int | gold dataset 의 sample 수 |
| `measured_samples` | int | gold ∩ prediction 의 sample 수 |
| `missing_count` | int | prediction 누락 sample 수 |
| `missing_ids` | list | 누락 sample id (최대 20개 절단) |
| `extra_count` | int | gold 에 없는 prediction sample 수 |
| `extra_ids` | list | 초과 sample id (최대 20개 절단) |
| `gold_duplicate_count` | int | gold 측 sample_id 중복 수 |
| `gold_duplicate_ids` | list | 중복 gold sample id |
| `prediction_duplicate_count` | int | prediction 측 sample_id 중복 수 |
| `prediction_duplicate_ids` | list | 중복 prediction sample id |
| `fail_class` | str\|null | 아래 fail_class 분류 (정합 시 null) |

이 검사는 F1 / precision / recall / ECE / deadline rate / 기타 모든
downstream aggregate 산출 **이전에** 수행되어야 한다. coverage 가 정합하지
않으면 측정을 중단하고 fail-closed 한다 (silent skip 금지).

## fail_class 분류

| fail_class | 조건 | 우선순위 |
|---|---|---|
| `GOLD_SAMPLE_ID_DUPLICATE` | gold 측 sample_id 중복 | 1 (최상위) |
| `FULL_EVAL_COVERAGE_MISMATCH` | missing / extra / prediction 중복 | 2 |
| `SEMANTIC_LABEL_VIOLATION` | gold label 이 schema enum 위반 | 별도 검사 |
| `ACTION_UNIT_MISMATCH` | action unit 분할 단위 불일치 | 별도 검사 |
| `AB_COMPOSITION_MISMATCH` | AB 구성 불일치 (Standard 7 연계) | 별도 검사 |

gold 중복은 prediction 중복/누락보다 우선 분류한다 — gold 가 오염되면
모든 하위 측정의 분모가 신뢰 불가이기 때문이다. 정합 시 `fail_class` 는
`null` 이며, 이때 `gold_duplicate_count == 0` 이고
`missing_count == extra_count == prediction_duplicate_count == 0` 이다.

## mode 분리 산식 정합 원칙 (PR #727 정합)

baseline 측정과 patched 측정은 서로 다른 actionable / 예측 소스를
사용해야 한다.

- `baseline` mode → patch 이전 원본 필드 (예: pre-patch `deadline_is_actionable`)
- `patched` mode → patch 후 산출 값 (예: `d2_classify` 의 `patched_actionable`)

두 mode 가 동일 pre-patch 필드를 공유하면 patch 효과가 측정에 반영되지
않으며, safety gate (false_deadline_rate 등) 의 판정 신뢰도가 훼손된다.
산출물에는 `mode` 와 `computed_from_*` 플래그를 명시하여 어떤 산식으로
측정했는지 추적 가능하게 한다. 미지정 mode 는 `ValueError` 로 fail-closed.

## 의무 적용 범위

- 모든 평가 PR (`scripts/eval/*` 변경) 에 자동 적용된다.
- coverage_report 12 필드 + fail_class 정합을 sentinel test 로 검증한다.
- CI guard `check_standard_09.py` 가 evidence 의 모든 `coverage_report.json`
  을 감사한다.
- 회귀 감지 → Codex 봇 검토 → 재검토팀 5단 검토로 정합을 교차 확인한다.

## Standard 6 와의 관계

Standard 6 (Coverage fail-closed sentinel) 은 Standard 9 에 흡수된다.
Standard 6 의 모든 의무 검사는 Standard 9 의 coverage_report 12 필드
및 fail_class 분류로 일반화되며, 기존 평가 PR 의 Standard 6 sentinel 은
그대로 유효하다 (회귀 없음).
