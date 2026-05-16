<!--
평가 PR 전용 template (scripts/eval/* · tests/eval/* · evidence/day*/ 변경).
운영 표준 1~12 자동 적용. 일반 PR 은 기본 template 을 사용한다.
-->

## STATUS

STATUS=<MEASURED_ONLY | PATCH_CONTINUE | HOLD>

<!-- PROCEED verdict 는 평가 PR 본문에 출현 금지 (Standard 12). -->

## 개요

- 이 평가 PR 의 목적 / Algorithm Branch 라벨 + GitHub PR 번호를 명시.
- 검토 기준 head SHA: 

## Standard 9 — Dataset Integrity Fail-Closed

- [ ] `coverage_report.json` 12 필드 정합 확인
- [ ] mode 분리 산식 정합 (baseline / patched 분리, `computed_from_*` 명시)
- [ ] `fail_class` 정확 산출 (GOLD_SAMPLE_ID_DUPLICATE / FULL_EVAL_COVERAGE_MISMATCH 등)
- [ ] coverage fail-closed sentinel test 추가
- [ ] CI guard `check_standard_09.py` 통과

## Standard 12 — Honest Reporting Pattern

- [ ] `expected_vs_observed` 명시 (인계 기대치 vs 실측)
- [ ] delta 정직 보고 (positive / negative / zero — 0 이어도 명시)
- [ ] natural shortage 명시 (`natural_shortage_note`)
- [ ] 측정값 임의 조정 0건
- [ ] verdict 경계 정합 (PROCEED verdict 금지)
- [ ] latent bug 패턴 점검 (추정 vs 실측 괴리 시 원인 재평가)

## 회귀 monitor

- [ ] Branch B-2 회귀 0건 (action_fp 234 유지)
- [ ] Branch D-1/D-3/D-4 회귀 0건 (deadline_f1 ≥ 0.8702)
- [ ] safety 6종 모두 유지 (false_deadline_rate / no_action_fp_rate / g22 / g23 등)

## sentinel test

- [ ] multiset / weighted invariant sentinel (Standard 4)
- [ ] coverage fail-closed sentinel (Standard 9)
- [ ] stratified composition sentinel — AB/sampled 평가 시 (Standard 7)
- [ ] AB variant distinctness — metric-only (Standard 11)

## forbidden grep

- [ ] forbidden 10 패턴 + Standard 12 확장 패턴 0건
- [ ] CI guard `check_standard_12.py` 통과

## 운영 표준 1~12 점검

- [ ] Standard 1/2 — evidence 정정 시 PR body 전체 동기 + 최신 head SHA 인용
- [ ] Standard 3 — 7 거버넌스 그룹 외 임의 팀명 미사용
- [ ] Standard 5 — Algorithm Branch 라벨과 GitHub PR 번호 분리 표기
- [ ] Standard 8 — Codex thread 동기화 (정정 후 새 head SHA 명시)
