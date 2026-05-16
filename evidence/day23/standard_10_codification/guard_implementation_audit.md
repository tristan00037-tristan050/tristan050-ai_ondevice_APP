# CI Guard Implementation Audit — Codex P1 2건 정정

## metadata
- source_pr: 729
- correction_cycle: Codex P1 (2건)
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## 정정 대상

Codex P1 2건 — 모두 `scripts/ci/check_standard_10.py` 자체 구현 정합 결함.
Standard 10 specification / PR template 은 변경하지 않음 (guard
implementation + sentinel 한정).

## P1-A — audit_evidence() fail-open (PR #728 P1-C 동일 패턴 재발)

- 결함: `audit_evidence()` 가 `before_after_comparison.json` /
  `policy_drift_report.json` 0건이어도 `ok=true` (fail-open) — Standard 10
  enforcement 가 우회 가능.
- 정정: PR #728 P1-C 패턴 적용
  - `find_evaluation_evidence_dirs()` (Standard 9) 를 import 재사용 — 단일
    정의 (재구현 회피).
  - `missing_required_artifact = bool(eval_dirs) and not ba_files` 플래그.
  - `ok = (not violations) and (not missing_required_artifact)` — return
    라인에서 두 fail-closed 신호 명시 합산.
  - 누락 시 `fail_class=STANDARD_10_BEFORE_AFTER_MISSING` violation.
  - return dict 에 `missing_required_artifact` + `eval_evidence_dirs_count`
    노출.

### 적용 시점 cutoff (소급 false-fail 방지)

`find_evaluation_evidence_dirs()` 는 저장소 전체를 스캔하여 day15~21 의
branch_* 평가 evidence 까지 검출한다. Standard 10 은 정착(PR #729, day23)
**이후** 평가 PR 부터 의무 적용되므로, day15~21 evidence 를 before/after
소급 요구 대상에 넣으면 정착 PR 자체의 guard 가 false-fail 한다.

- `STANDARD_10_ACTIVE_FROM_DAY = 24` cutoff 도입 — Standard 10 적용
  대상은 day24 이상 평가 evidence 로 한정.
- cutoff 는 **scan 범위 제한이 아니라 적용 시점 경계** (scan 은
  `evidence/day*/` 전체 유지 — PR #728 P1-B 의 hardcoded scan 결함과 무관).
- 실측: `audit_evidence(ROOT)` — eval_dirs 0 (day15~21 cutoff 제외) /
  missing_required_artifact false / ok true.

## P1-B — validate_drift_report() negative drift_rate 미차단

- 결함: `drift_rate` 가 음수일 때 검증 없음 — `drift_rate=-0.3` +
  `drift_class="OK"` 통과 가능. drift 가 음수 부호로 `OK` 등급에 은폐.
- 정정: `validate_drift_report()` 에 음수 차단 추가
  - `drift_rate` 가 수치형이 아니면 위반.
  - `drift_rate < 0` → `NEGATIVE_DRIFT_RATE` 위반 (drift 는 변화의
    절대비율이므로 항상 비음수).
  - `drift_rate` 누락은 기존 `DRIFT_REPORT_FIELDS` 필드 검사로 이미 차단.
- 검증: sentinel #8 — 음수 drift_rate 차단, 비음수 통과, 누락 차단.

## 정직 보고 — PR #728 P1-C 학습 미전수

P1-A 는 PR #728 P1-C 와 **동일 패턴의 결함(fail-open audit)** 이다.
PR #728 에서 `find_evaluation_evidence_dirs` + `missing_required_artifact`
패턴을 정착시켰으나, PR #729 Standard 10 의 `audit_evidence()` 초안에
그 학습을 전수하지 못했다. 정정은 PR #728 패턴을 그대로 재사용 — 동일
패턴 재발을 정직하게 기록한다 (Standard 12 latent-pattern 보고).

## 정정 영향 범위

- 변경: scripts/ci/check_standard_10.py, tests/standards/ 1파일 (sentinel +3).
- 불변: Standard 9/10/12 specification, PR template, 알고리즘/모델/임계값,
  main 측정값 (deadline_f1 0.8702 / action_fp 234 / safety 6종).

## expected vs observed

- expected: Codex P1 2건 정정 (audit fail-closed + negative drift_rate 차단)
- observed: 2건 모두 정정 완료 — PR #728 P1-C 패턴 재사용으로 fail-open
  차단, NEGATIVE_DRIFT_RATE 신설
- delta: sentinel +3 (19 → 22), fail-open 경로 차단, main 측정값 변동 0건

## verdict: MEASURED_ONLY
