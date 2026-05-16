# Sentinel Test Design — Standard 9 / 12

## metadata
- source_pr: 728
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## tests/standards/test_standard_09_dataset_integrity.py (7건)

| # | 테스트 | 검증 |
|---|---|---|
| 1 | test_coverage_report_12_fields_required | COVERAGE_REPORT_FIELDS 12개 + 필드 누락 시 fail-closed |
| 2 | test_gold_duplicate_fail_closed | gold 중복 → GOLD_SAMPLE_ID_DUPLICATE + report 정합 |
| 3 | test_prediction_duplicate_fail_closed | pred 중복/missing → FULL_EVAL_COVERAGE_MISMATCH, gold 우선 |
| 4 | test_mode_separation_required | baseline/patched mode 분리 + 미지정 mode ValueError |
| 5 | test_d2_actionable_산식_정합 | d2_classify INQUIRY non-actionable / orig_actionable 보존 |
| 6 | test_coverage_report_missing_fail_closed | 평가 evidence + coverage 0건 → ok=false (Codex P1-C) |
| 7 | test_coverage_report_missing_fail_closed_actual_path | audit_evidence() return path — ok / missing_required_artifact 정합 (P1-C 명확) |

## tests/standards/test_standard_12_honest_reporting.py (7건)

| # | 테스트 | 검증 |
|---|---|---|
| 1 | test_expected_vs_observed_required | expected_vs_observed / observed 누락 시 위반 |
| 2 | test_delta_zero_must_be_reported | delta 키 누락 시 위반, delta=0.0 명시는 정합 |
| 3 | test_natural_shortage_must_be_specified | natural_shortage=true + note 미명시 시 위반 |
| 4 | test_no_proceed_verdict_in_measured_only_pr | 금지 verdict 토큰 출현 → 위반, ALLOWED_STATUS 검증 |
| 5 | test_latent_bug_pattern_정합 | 관측 < 추정 × 0.5 → 재평가 의무, 임의 조정 패턴 탐지 |
| 6 | test_proceed_filter_no_runtime_crash | 금지 verdict 필터 crash 0건 / line·context 판정 (Codex P1-A) |
| 7 | test_evidence_scan_covers_all_day_folders | day23/day99 검출 — hardcoded day22 회귀 차단 (Codex P1-B) |

## 정합 원칙

- 모든 sentinel 은 CI guard 의 reusable API 또는 PR #727 실제 코드
  (measure_deadline / d2_classify) 를 import 하여 결정적으로 검증.
- 임의 fixture / tmp_path 사용 시 측정값 변동 없음 (단위 로직 검증 한정).
- 신규 sentinel 14건 (정착 10 + Codex P1 정정 3 + P1-C 명확 1) — 회귀 가산.

## 측정 결과

- tests/standards/ : 14 passed (정착 10 + Codex P1 정정 3 + P1-C 명확 1)
- 알고리즘/모델 미변경 — main 측정값 변동 0.

## verdict: MEASURED_ONLY
