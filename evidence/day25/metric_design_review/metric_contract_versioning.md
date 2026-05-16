# Metric Contract Versioning (Standard 10 정합)

## metadata
- source_pr: 731
- branch: Metric-Design-Review
- verdict: MEASURED_ONLY

## Standard 10 정합

본 PR 은 평가 계약(metric contract)을 변경하므로 Standard 10 (Strict
Policy Base Drift)의 version bump 의무가 적용된다.

## contract version v1.0.0 (PR #730 머지 후 현재)

- `normalized_action_f1` (strict extraction)
- `deadline_f1`
- safety 6종
- 단일 Layer — strict only.

## contract version v2.0.0 (본 PR 후)

- **Layer 1** `strict_action_f1` = `normalized_action_f1` (산식 변경 없음).
- **Layer 2** 보조 지표 5종:
  - `product_equivalent_action_rate`
  - `dangerous_over_extraction_rate`
  - `manual_suggestion_precision` (Internal Alpha feedback 후 측정)
  - `suggestion_value_adjusted_f1` (연구용 — production 금지)
  - (`strict_action_f1` 은 Layer 1 과 공유)
- `deadline_f1`, safety 6종 동일 유지.

## SemVer 분석

- 변경 성격: 계약 본질 변경 (단일 Layer → 2 Layer 분리).
- MAJOR bump: `v1.0.0` → `v2.0.0`.
- `is_version_bumped("1.0.0", "2.0.0")` = true (Standard 10 정합).

## before/after comparison

| metric | before | after | delta |
|---|---|---|---|
| strict_action_f1 | 0.6182 | 0.6182 | 0 |
| deadline_f1 | 0.8702 | 0.8702 | 0 |
| action_fp | 234 | 234 | 0 |

- Layer 1 (strict_action_f1): 산식·값 불변 — delta 0 보증.
- Layer 2 보조 지표: before 미정의 → after 신규 정의. 기존 지표를 바꾸지
  않으므로 drift 가 아니라 계약 확장이다.

## policy drift

- `drift_rate`: 0.0 — strict layer 산식 변경 없음.
- `drift_class`: `OK` (drift_rate < 5%).
- `samples_compared`: 67.
- 새 보조 지표 추가는 contract version bump 이며 strict layer drift 아님.

## STANDARD_10_ACTIVE_FROM_DAY cutoff

본 PR evidence 는 day25 — `STANDARD_10_ACTIVE_FROM_DAY = 24` 이후이므로
Standard 10 적용 대상. `before_after_comparison.json` /
`policy_drift_report.json` 산출물을 포함한다.
