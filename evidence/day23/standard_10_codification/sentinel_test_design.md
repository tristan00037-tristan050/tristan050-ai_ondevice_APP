# Sentinel Test Design — Standard 10

## metadata
- source_pr: 729
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## tests/standards/test_standard_10_strict_policy_base_drift.py (8건)

| # | 테스트 | 검증 |
|---|---|---|
| 1 | test_metric_threshold_change_detected | 정착 기준 그대로 → 0건, deadline_f1/auto_apply_precision 변경 검출 |
| 2 | test_label_guide_version_bump_required | parse_semver / is_version_bumped — 증가만 bump, 형식 위반 ValueError |
| 3 | test_before_after_comparison_required | comparison 필드 누락 / delta 불일치 → 위반 |
| 4 | test_policy_drift_threshold_5_percent | <5% OK / 5~20% PATCH_CONTINUE / ≥20% HOLD |
| 5 | test_drift_report_format_정합 | drift report 필드 / version bump / drift_class↔rate 정합 |
| 6 | test_audit_evidence_fail_closed_when_artifacts_missing | 평가 evidence + before_after 0건 → ok=false (Codex P1-A) |
| 7 | test_audit_evidence_passes_for_codification_pr | 정착 PR / 정착 이전(day<24) evidence 통과 (Codex P1-A) |
| 8 | test_validate_drift_report_rejects_negative_rate | 음수 drift_rate → NEGATIVE_DRIFT_RATE (Codex P1-B) |

## 정합 원칙

- 모든 sentinel 은 CI guard `check_standard_10.py` 의 reusable API 를
  import 하여 결정적으로 검증.
- 임의 fixture / tmp_path 사용 — 측정값 변동 없음 (단위 로직 검증 한정).
- 신규 sentinel 8건 (정착 5 + Codex P1 정정 3) — 회귀 카운트에 가산.

## 측정 결과

- tests/standards/test_standard_10_strict_policy_base_drift.py : 8 passed
- tests/standards/ 누적 : 22 passed (PR #728 정착 14 + Standard 10 8)
- 알고리즘/모델 미변경 — main 측정값 변동 0.

## verdict: MEASURED_ONLY
