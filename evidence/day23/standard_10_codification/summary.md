# PR #729 — Standard 10 Codification Summary

## metadata
- dataset_id: card1_evalset_v1_1_500
- source_pr: 729
- source_merge_sha: 64817870 (PR #728)
- codification_type: operating_standard
- verdict: MEASURED_ONLY
- generated_at: 2026-05-16

## Scope

운영 표준 Standard 10 (Strict Policy Base Drift) 정착 PR. 알고리즘 / 모델 /
vocabulary / safety threshold 변경 없음 — 문서 + CI guard + sentinel +
PR template 갱신만 추가.

## 정직 보고 — 본 PR 의 본질

- 본 PR 은 **신규 결함 수정이 아니라 정착 PR** 이다. Standard 10 은 자문
  4차 8 의 시급 권고를 Branch C-lite 직전에 정착하는 것.
- 직전 cycle (PR #728) 정합성: Standard 9 / 12 + CI guard 2종 + sentinel
  14건 main 정착 완료 (merge SHA 64817870). PR #728 Codex P1 3건은 모두
  정정 완료, P1-C 는 return 라인 명확 처리로 해소.
- existing PR audit 결과: PR #720~#728 metric threshold 변경 0건 / label
  guide 변경 0건 / policy drift 0건 — Standard 10 사실상 충족, 소급
  재작성 없음.
- 정착 PR 이므로 Codex P1 0건 기대 (알고리즘/측정 변경 없음).

## Standard 8 한계 발견 (별도 강화 안건)

PR #728 P1-C cycle 에서 관찰: Codex review thread 가 정정 commit 의 새
head 로 `commit_id` 가 갱신되고 line 이 remap 되더라도, thread 의
`diff_hunk` 는 원본(정정 전) 코드를 유지할 수 있다. 이 경우 outdated
thread 와 신규 정정의 구분이 어렵다. Standard 8 (Codex thread
synchronization) 의 outdated 판정 기준에 `diff_hunk` 대조를 추가하는 것이
바람직 — 본 PR 범위 밖, 별도 강화 안건으로 기록.

## Standard 10 — Strict Policy Base Drift

- 정착 문서: docs/operating-standards/standard-10-strict-policy-base-drift.md
- metric threshold 변경 금지 (5종 정착 기준)
- label guide version bump 의무 (SemVer)
- before/after comparison 형식 표준
- old/new policy drift report + drift 등급 (5% / 20%)

## CI guard

- scripts/ci/check_standard_10.py — metric threshold 변경 / version bump /
  before-after / drift report 감사. reusable API 9종 + main().

## PR template

- .github/PULL_REQUEST_TEMPLATE/eval_pr.md — Standard 10 체크리스트 추가
  (Standard 12 섹션과 회귀 monitor 사이)

## sentinel test (신규 5건)

- tests/standards/test_standard_10_strict_policy_base_drift.py — 5건 PASS

## existing PR compliance audit (PR #720~#728)

- metric threshold 변경 0건 / label guide 변경 0건 / policy drift 0건
- before/after 는 #724/#727 에서 사실상 수행 — 형식만 정착으로 표준화
- 소급 재작성 없음 (honest)

## expected vs observed

- expected: Standard 10 정착 (문서 + CI guard + sentinel + template 갱신)
- observed: 정착 완료 — 신규 sentinel 5건 PASS, CI guard 정상 동작
- delta: 신규 sentinel +5 (회귀 가산), main 측정값 변동 0건

## main 측정값 정합 (변동 0건)

- deadline_f1 0.8702 / action_fp 234 / safety 6종 — 모두 불변 (알고리즘
  미변경)

## verdict: MEASURED_ONLY

정착 PR — 금지 verdict 미사용. forbidden grep 10 패턴 0건.
