# Dataset Integrity Coverage Audit (Codex P1 — 강화 안건 16)

## metadata
- source_pr: 734
- branch: Final-Beta-Readiness-Measurement
- correction_cycle: Codex P1 (dataset integrity coverage_mismatch)
- verdict: MEASURED_ONLY

## Codex P1 결함 본질 — PR #730 패턴 latent gap

PR #730 에서 정착한 `detect_duplicates()` fail-closed 패턴은 **duplicate
sample_id 만** 차단했다. PR #734 의 coverage 산출은 `missing_count` /
`missing_ids` 를 hardcoded `0` / `[]` 로 두어, `mixed_id_list` 의 sample 이
dataset row 또는 prediction row 에서 누락되어도 fail-open 으로 통과했다.

이는 단순 결함이 아니라 **PR #730 패턴 자체의 latent gap** 이다. 정정
cycle 패턴 6회 안정화(PR #728~#733) 완성 후 처음 발견된 한계로, Codex
봇이 패턴 자체의 누락 영역을 사전 발견한 거버넌스 안전망 진화 사례다.

## 정정 — PR #730 패턴 확장

`compute_coverage(mixed_id_list, dataset_ids, pred_id_list)` 함수:

| 차단 영역 | 출처 | fail_class |
|---|---|---|
| source sample_id 중복 | PR #730 패턴 | SOURCE_SAMPLE_ID_DUPLICATE |
| prediction sample_id 중복 | PR #730 패턴 | FULL_EVAL_COVERAGE_MISMATCH |
| **missing from dataset** | **본 PR 확장** | FULL_EVAL_COVERAGE_MISMATCH |
| **missing from predictions** | **본 PR 확장** | FULL_EVAL_COVERAGE_MISMATCH |

- `missing_from_dataset = required_ids − dataset_ids`
- `missing_from_predictions = required_ids − pred_ids`
- `measured_samples = expected_samples − missing_count`
- missing 발견 시 `FULL_EVAL_COVERAGE_MISMATCH` + downstream 차단 (return 1).

## dataset integrity coverage_mismatch 표준 (강화 안건 16)

dataset integrity gate 는 다음을 모두 차단한다:

1. **duplicate** — source / prediction sample_id 중복 (PR #730 패턴).
2. **missing** — required sample 이 dataset / predictions 에서 누락
   (본 PR 확장).
3. **measured vs expected 정량 비교** — `measured_samples` 는 실제
   계산값이어야 하며 hardcoded 금지.

향후 모든 dataset integrity PR 은 duplicate + missing 을 동시에 차단한다.

## fail-closed 회귀 sentinel

- `#11` mixed_id_list 가 dataset 에서 누락 → FULL_EVAL_COVERAGE_MISMATCH.
- `#12` mixed_id_list 가 predictions 에서 누락 → FULL_EVAL_COVERAGE_MISMATCH.
- `#13` source / prediction duplicate fail-closed 유지 (PR #730 패턴 회귀 차단).

## 측정값 영향 (정직 보고 — 시나리오 1)

MIXED-A 67건은 dataset 500 / predictions 500 에 전부 존재한다:
- missing_from_dataset 0 / missing_from_predictions 0 / missing_count 0
- expected_samples 67 == measured_samples 67 / fail_class null

정정 전후 분포 불변 — P1 은 latent gap 의 선제 정정이며 측정값 임의
조정이 아니다. Standard 9 (Dataset Integrity Fail-Closed)의 본질적 강화
사례 (Standard 12-J 안건 정량 기반).
