# Standard 10 — Strict Policy Base Drift Specification

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 729
- source_merge_sha: 64817870 (PR #728)
- codification_type: operating_standard
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## 정착 목적

평가 결과의 시계열 비교가 의미를 가지려면 평가 기준 자체가 시간에 따라
흔들리지 않아야 한다 (base drift 차단). 자문 4차 8 — Branch C-lite / 정밀
patch 진입 전 Standard 10 정착 시급 권고.

## 원칙 1 — metric threshold 변경 금지

정착 평가 기준 (check_standard_10.METRIC_THRESHOLDS):

| metric | threshold | 방향 |
|---|---|---|
| deadline_f1 | 0.86 | 외부 베타 기준 (하향 금지) |
| normalized_action_f1 | 0.75 | 기준 (하향 금지) |
| false_deadline_rate | 0.02 | safety gate 상한 (상향 금지) |
| no_action_fp_rate | 0.03 | safety gate 상한 (상향 금지) |
| auto_apply_precision | 0.95 | 하향 절대 금지 |

`detect_metric_threshold_changes()` 가 평가 PR threshold 를 정착 기준과
대조 — 변경 키 검출 시 fail-closed.

## 원칙 2 — label guide version bump (SemVer)

label guide 변경 시 SemVer (MAJOR.MINOR.PATCH) version bump 의무.
대상: normalized_action label set / deadline strength taxonomy
(HARD/SOFT/INQUIRY/URGENCY/CONDITION/NONE) / safety policy.
`parse_semver()` / `is_version_bumped()` 가 형식·증가 검증.

## 원칙 3 — before/after comparison 필수

정밀 patch PR 은 patch 전 baseline vs patch 후 측정값 비교 표 의무.
필수 필드: metric / before / after / delta. delta = after − before
(positive/negative/zero 모두 정직 보고 — Standard 12 연계).

## 원칙 4 — old/new policy drift report

policy 변경 시 drift report 작성. 필수 필드: policy_name /
old_policy_version / new_policy_version / drift_rate / drift_class /
samples_compared.

## drift threshold 등급

drift_rate = |new − old| / |old|:

| drift_rate | drift_class | 처리 |
|---|---|---|
| < 5% | OK | 비교 가능성 유지 |
| 5%~20% | PATCH_CONTINUE | drift 명시 + 추가 cycle |
| ≥ 20% | HOLD | 정착 보류 — base drift 과다 |

## 산출물 정합

- 정착 문서: docs/operating-standards/standard-10-strict-policy-base-drift.md
- CI guard: scripts/ci/check_standard_10.py
- sentinel: tests/standards/test_standard_10_strict_policy_base_drift.py (5건)
- PR template: .github/PULL_REQUEST_TEMPLATE/eval_pr.md (Standard 10 체크리스트)

## verdict: MEASURED_ONLY (정착 PR — 알고리즘 변경 없음)
