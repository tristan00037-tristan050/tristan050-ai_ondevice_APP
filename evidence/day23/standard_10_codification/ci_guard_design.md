# CI Guard Design — Standard 10

## metadata
- source_pr: 729
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## scripts/ci/check_standard_10.py — Strict Policy Base Drift

PR #728 정착 패턴 정합 — reusable API + main(). 알고리즘/모델/임계값
미변경, 평가 PR 의 정책 drift 만 검사.

reusable API:
- `METRIC_THRESHOLDS` — 정착 평가 기준 5종 (deadline_f1 0.86 /
  normalized_action_f1 0.75 / false_deadline_rate 0.02 /
  no_action_fp_rate 0.03 / auto_apply_precision 0.95)
- `DRIFT_PATCH_CONTINUE` (0.05) / `DRIFT_HOLD` (0.20) — drift 등급 경계
- `LABEL_GUIDE_TARGETS` — version bump 대상 label guide 3종
- `BEFORE_AFTER_FIELDS` / `DRIFT_REPORT_FIELDS` — 필수 필드 정의
- `parse_semver(version)` — 'MAJOR.MINOR.PATCH' → tuple, 형식 위반 ValueError
- `is_version_bumped(old, new)` — new SemVer 가 old 대비 증가 여부
- `detect_metric_threshold_changes(candidate)` — 정착 기준 대비 변경 키 목록
- `classify_drift(old, new)` — drift 비율 → OK / PATCH_CONTINUE / HOLD
- `validate_before_after(report)` — before/after comparison 형식 + delta 정합
- `validate_drift_report(report)` — drift report 필드 + version bump +
  drift_class↔drift_rate 정합
- `audit_evidence(root)` — evidence/day*/ before_after / drift report 감사

main(): `audit_evidence(ROOT)` 실행, 위반 시 exit 1.

## 검출 기능

| 기능 | API | 동작 |
|---|---|---|
| metric threshold 변경 | detect_metric_threshold_changes | 정착 기준 ≠ candidate → 변경 키 |
| label guide version bump | is_version_bumped | new ≤ old → 위반 |
| before/after 누락 | validate_before_after | comparison 필드/Δ 불일치 → 위반 |
| drift threshold | classify_drift | 5%↑ PATCH_CONTINUE / 20%↑ HOLD |
| drift report 형식 | validate_drift_report | 필드/version/class 불일치 → 위반 |

## 측정 영향

알고리즘/모델/임계값 미변경. evidence 텍스트·JSON 정합만 검사 — main
측정값 (deadline_f1 0.8702 / action_fp 234 / safety 6종) 변동 0.

## verdict: MEASURED_ONLY
