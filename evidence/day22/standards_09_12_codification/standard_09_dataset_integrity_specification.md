# Standard 9 — Dataset Integrity Fail-Closed Specification

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 728
- codification_type: operating_standard
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## 정착 목적

Standard 6 (Coverage fail-closed sentinel) 이 PR #718 / #722 / #723 / #725 /
#726 의 5회 회귀를 입증 → dataset-level integrity 를 단일 표준으로 승격.
자문 4차 8: mixed/action unit dataset-level integrity 가 결정적.

## coverage_report 12 필드

coverage_checked, expected_samples, measured_samples, missing_count,
missing_ids, extra_count, extra_ids, gold_duplicate_count,
gold_duplicate_ids, prediction_duplicate_count, prediction_duplicate_ids,
fail_class — 총 12 필드. F1/precision/recall/ECE/deadline rate 산출 이전
필수 검사.

## fail_class 분류

| fail_class | 조건 | 우선순위 |
|---|---|---|
| GOLD_SAMPLE_ID_DUPLICATE | gold sample_id 중복 | 1 |
| FULL_EVAL_COVERAGE_MISMATCH | missing / extra / prediction 중복 | 2 |
| SEMANTIC_LABEL_VIOLATION | gold label schema enum 위반 | 별도 |
| ACTION_UNIT_MISMATCH | action unit 분할 단위 불일치 | 별도 |
| AB_COMPOSITION_MISMATCH | AB 구성 불일치 (Standard 7 연계) | 별도 |

## mode 분리 산식 정합 원칙 (PR #727 정합)

baseline → pre-patch 원본 필드 / patched → patch 후 산출값. 두 mode 가
동일 pre-patch 필드를 공유하면 patch 효과 미반영 → safety gate 판정
신뢰도 훼손. 산출물에 mode + computed_from_* 명시. 미지정 mode 는
ValueError fail-closed.

## 산출물 정합

- 정착 문서: docs/operating-standards/standard-09-dataset-integrity.md
- CI guard: scripts/ci/check_standard_09.py
- sentinel: tests/standards/test_standard_09_dataset_integrity.py (5건)
- Standard 6 는 Standard 9 에 흡수 (기존 sentinel 회귀 없음)

## verdict: MEASURED_ONLY (정착 PR — 알고리즘 변경 없음)
