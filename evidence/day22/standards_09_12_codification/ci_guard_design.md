# CI Guard Design — Standard 9 / 12

## metadata
- source_pr: 728
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## scripts/ci/check_standard_09.py — Dataset Integrity Fail-Closed

reusable API:
- `COVERAGE_REPORT_FIELDS` — coverage_report 필수 12 필드
- `FAIL_CLASSES` — 허용 fail_class 집합 (5종)
- `classify_coverage(item_ids, pred_ids)` — gold/pred id → fail_class
  - 우선순위: gold 중복 > (missing | extra | prediction 중복)
- `validate_coverage_report(cov)` — coverage_report dict → 위반 목록
  - 12 필드 존재 / fail_class 정합 / count↔ids 정합 검사
- `audit_evidence(root)` — evidence/**/coverage_report.json 전수 감사

main(): evidence 하위 모든 coverage_report.json 감사, 위반 시 exit 1.

## scripts/ci/check_standard_12.py — Honest Reporting Pattern

reusable API:
- `FORBIDDEN_PATTERNS` — 기존 forbidden grep 10 패턴
- `STANDARD_12_PATTERNS` — 확장 5 패턴 (측정값 임의 조정 / threshold 하향 /
  실패 은폐 / 회귀 은폐 / 테스트 완화 통과)
- `ALLOWED_STATUS` — {MEASURED_ONLY, PATCH_CONTINUE, HOLD}
- `scan_forbidden(text)` — forbidden 10 + 확장 5 매칭 목록
- `validate_status_line(text)` — STATUS 토큰 정합 + 금지 verdict 부재 검증
- `validate_honest_report(report)` — expected_vs_observed / delta / natural
  shortage 명시 검증
- `requires_root_cause_reeval(expected, observed)` — 추정 vs 실측 괴리
  (관측 < 추정 × 0.5) → 재평가 의무 여부 (PR #725 정합)

main(): evidence/day22/**/summary.md forbidden 패턴 0건 검증, 위반 시 exit 1.

## forbidden grep 패턴 확장

기존 10 패턴은 `tests/eval/test_forbidden_strings_day14.py` 의
`FORBIDDEN_PATTERNS` 정의를 그대로 재사용한다 (production readiness 류
표현 + 금지 verdict 토큰). 본 evidence 는 패턴 문자열을 직접 나열하지
않는다 (자기참조 매칭 방지).

Standard 12 확장 5 패턴은 `check_standard_12.py` 의 `STANDARD_12_PATTERNS`
에 정의 — 측정값 수기 보정 / 임계값 하향 / 실패 은폐 / 회귀 은폐 / 테스트
완화 통과 신호를 차단한다.

## 측정 영향

알고리즘/모델/임계값 미변경. evidence 텍스트·JSON 정합만 검사 — main
측정값 (deadline_f1 0.8702 / action_fp 234 / safety 6종) 변동 0.

## verdict: MEASURED_ONLY
