# CI Guard Implementation Audit — Codex P1 3건 정정

## metadata
- source_pr: 728
- correction_cycle: Codex P1 (3건)
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## 정정 대상

Codex P1 3건 — 모두 CI guard 자체 구현 정합 결함. Standard 9/12
specification / PR template 은 변경하지 않음 (guard implementation 한정).

## P1-A — check_standard_12.py 금지 verdict 필터 lookbehind 제거

- 결함: `(?<!금지[^\n]{0,4})` 는 가변폭 lookbehind — Python `re` 미지원,
  금지 verdict 토큰 포함 텍스트 scan 시 `re.error` runtime crash.
- 정정: `is_proceed_violation_in_text()` 신설 — line 단위 스캔 + 같은 line
  부정 단어(절대/금지/불가/prohibit/forbidden) 동반 시 설명문 제외.
- fixed-width regex 만 사용 (금지 verdict 토큰 word-boundary 매칭 + 부정
  단어 alternation).
- 검증: sentinel #6 `test_proceed_filter_no_runtime_crash` — crash 0건,
  설명문 pass / 위반문 violation 판정 정합.

## P1-B — check_standard_12.py scan 범위 확장

- 결함: `evidence/day22/**/summary.md` hardcoded — day23+ 폴더로 영구 우회.
- 정정: `evidence/day*/**/summary.md` — 전 day 폴더 scan. main() 을
  `audit_summaries(root)` 로 분리 (root 주입 가능 → 테스트 가능).
- 검증: sentinel #7 `test_evidence_scan_covers_all_day_folders` —
  day22/day23/day99 모두 검출.
- 실측: CI guard 12 scan 대상 9건 (day15~day22), 위반 0건.

## P1-C — check_standard_09.py coverage_report 0건 fail-closed

- 결함: `audit_evidence()` 가 coverage_report.json 0건이면 `ok=true`
  (fail-open) — 평가 evidence 가 있어도 coverage 누락이 우회됨.
- 정정: `find_evaluation_evidence_dirs()` 신설 (branch_* + summary.md /
  ab_*.json / full_eval_*.json 검출). 평가 evidence 존재 + coverage_report
  0건 → `fail_class=COVERAGE_REPORT_MISSING` violation, `ok=false`.
- `eval_evidence_dirs_count` 보고 필드 추가.

### P1-C 명확 처리 (return 라인 정합 재정정)

Codex P1-C thread 가 head 43c1eb29 line 165 (audit_evidence return)에
remap 된 채 잔존 — thread 의 `diff_hunk` 는 fail-closed 미적용 원본 코드
(@@ -0,0 +1,139 @@) 로, 원 코멘트가 line 번호만 갱신된 상태 (Standard 8
outdated-thread). 그러나 thread 잔존 자체를 해소하기 위해 return 라인을
명확히 정합 처리한다.

- `missing_required_artifact` boolean 을 audit_evidence 산출물에 명시 추가
  (Codex P1-C 권고: "audit result 에 missing_required_artifact=true 명시").
- `ok` 산식을 return 라인에서 `(not violations) and (not
  missing_required_artifact)` 로 명시 — 두 fail-closed 신호를 모두 반영.
- return dict 가 두 신호(violations / missing_required_artifact)를 모두
  노출하여 CI 및 재검토팀이 diff 기준으로 해소를 입증 가능.
- 검증: sentinel #6 + #7 `test_coverage_report_missing_fail_closed_actual_path`
  — case 1 (evidence + coverage 0건 → ok=false, missing_required_artifact
  =true, checked=0) / case 2 (coverage 추가 → 해소) / case 3 (evidence 부재
  → ok=true).
- 실측: CI guard 09 — coverage_report 3건 / 평가 evidence 6 디렉토리,
  missing_required_artifact=false, fail-closed 미발동 (정합), ok=true.

## 정정 영향 범위

- 변경: scripts/ci/check_standard_09.py, scripts/ci/check_standard_12.py,
  tests/standards/ 2파일 (sentinel +3).
- 불변: Standard 9/12 specification, PR template, 알고리즘/모델/임계값,
  main 측정값 (deadline_f1 0.8702 / action_fp 234 / safety 6종).

## expected vs observed

- expected: Codex P1 3건 정정 (CI guard runtime 정합 + fail-closed)
- observed: 3건 모두 정정 완료 — variable-width lookbehind 제거 / scan
  범위 day* 확장 / coverage_report 0건 fail-closed
- delta: sentinel +3 (10 → 13), CI guard runtime crash 위험 제거,
  fail-open 경로 차단. main 측정값 변동 0건.

## verdict: MEASURED_ONLY
