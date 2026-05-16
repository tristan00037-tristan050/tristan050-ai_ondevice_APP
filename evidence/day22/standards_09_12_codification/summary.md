# PR #728 — Standard 9 / 12 Codification Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 728
- source_merge_sha: 86621dd90c83b74d80e144f5dd88c61f65c6f759 (PR #727)
- codification_type: operating_standard
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## Scope

운영 표준 Standard 9 (Dataset Integrity Fail-Closed) + Standard 12 (Honest
Reporting Pattern) 정착 PR. 알고리즘 / 모델 / vocabulary / safety threshold
변경 없음 — 문서 + CI guard + sentinel + PR template 만 추가.

## Standard 9 — Dataset Integrity Fail-Closed

- 정착 문서: docs/operating-standards/standard-09-dataset-integrity.md
- coverage_report 12 필드 명세 + fail_class 분류 5종
- baseline / patched mode 분리 산식 정합 원칙 (PR #727 정합)
- Standard 6 (Coverage fail-closed) 을 Standard 9 로 흡수 — 기존 sentinel
  회귀 없음
- 5회 회귀 입증: PR #718 / #722 / #723 / #725 / #726

## Standard 12 — Honest Reporting Pattern

- 정착 문서: docs/operating-standards/standard-12-honest-reporting.md
- expected_vs_observed 명시 의무 / delta 정직 보고 (0·음수 포함)
- natural shortage 명시 / verdict 경계 (금지 verdict 미사용)
- latent bug 패턴 (PR #725) / measurement integrity 우선 (PR #727)
- 측정값 수기 보정 금지

## CI guard

- scripts/ci/check_standard_09.py — coverage_report 12 필드 + fail_class 감사
- scripts/ci/check_standard_12.py — forbidden 패턴 + STATUS 라인 정합 감사

## PR template

- .github/PULL_REQUEST_TEMPLATE/eval_pr.md — 평가 PR 전용, 운영 표준 1~12
  체크리스트 자동 적용

## sentinel test (신규 10건)

- tests/standards/test_standard_09_dataset_integrity.py — 5건 PASS
- tests/standards/test_standard_12_honest_reporting.py — 5건 PASS

## existing PR compliance audit

- PR #725 / #726 / #727 독립 coverage_report.json 3종 — 12 필드 정합
- PR #720~#723 은 정착 이전 형태 — 소급 재작성 없음 (honest)
- verdict 경계: PR #720~#727 모두 MEASURED_ONLY / PATCH_CONTINUE

## expected vs observed

- expected: Standard 9 + 12 정착 (문서 + CI guard + sentinel + template)
- observed: 정착 완료 — 신규 sentinel 10건 PASS, CI guard 2종 정상 동작
- delta: 신규 sentinel +10 (회귀 가산), main 측정값 변동 0건

## main 측정값 정합 (변동 0건)

- deadline_f1 0.8702 — 불변 (알고리즘 미변경)
- action_fp 234 — 불변
- safety 6종 — 불변 (false_deadline_rate 0.014 등)

## verdict: MEASURED_ONLY

정착 PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.
