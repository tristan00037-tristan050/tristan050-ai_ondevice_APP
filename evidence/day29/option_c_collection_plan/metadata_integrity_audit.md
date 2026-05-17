# Metadata Integrity Audit (강화 안건 17)

## metadata
- actual_github_pr: 737
- legacy_handoff_label: PR #735+ (chat 인계 박스 표기)
- source_pr: 737
- branch: Option-C-Collection-Plan
- correction_cycle: 메타데이터 정합 정정
- verdict: MEASURED_ONLY

## 결함 본질

chat 인계 박스가 본 작업을 "PR #735+" 로 표기했으나, 실제 생성된 GitHub
PR 번호는 **#737** 이다 (#735·#736 은 이미 사용됨). 그 결과 PR title /
body / evidence 의 `source_pr` 가 `735` 로 고정되어 실제 GitHub PR 번호와
불일치했다 — 메타데이터 정합 결함.

## Claude 자기 적용 정직 인지

본 결함의 원인은 chat 인계 박스 작성 단계에서 "PR #735+" 표기를 사용하고,
GitHub 실제 PR 번호가 확정되기 전 그 번호를 evidence 에 고정한 데 있다.
인계 박스의 잠정 번호와 GitHub 실제 번호의 불일치를 사전 명시하지 못한
한계를 정직 인지한다 (Standard 12 자기 적용).

## 정정 (옵션 B — 파일명 유지 + 분리 기록)

- `actual_github_pr: 737` — 실제 GitHub PR 번호.
- `legacy_handoff_label: "PR #735+ (chat 인계 박스 표기)"` — 인계 박스 표기.
- `source_pr` 를 실제 번호 `737` 로 정정.
- script / test 파일명(`pr735_*.py`, `test_pr735_invariants.py`)은 유지 —
  git 이력 fragmentation 회피, 변경 최소화.

## PR 번호 정합성 메타데이터 무결성 표준

향후 모든 인계 박스 + PR 생성 시:

1. **actual_github_pr** — `gh pr create` 응답의 실제 PR 번호를 evidence
   metadata 에 기록한다.
2. **legacy_handoff_label** — 인계 박스의 잠정 표기를 별도 필드로 분리
   기록한다.
3. PR title / body 는 actual_github_pr 기준으로 작성하고, 잠정 표기와
   다를 경우 그 사실을 명시한다.
4. evidence 의 `source_pr` 는 actual_github_pr 와 일치시킨다.

## 측정값 영향 (정직 보고 — 시나리오 1)

본 정정은 메타데이터 정정만이다. main 측정값(strict_action_f1 0.6452 /
deadline_f1 0.8702 / action_fp 207 / safety 6종) delta 0, sentinel 18건
+ 회귀 정합 유지, 자문 6차 정합(M-1~M-14) 영향 0 — 분포 불변.

## 거버넌스 안전망 자기 진화 사례 2호

- 사례 1 (PR #734): PR #730 `detect_duplicates()` 패턴의 missing-samples
  latent gap — Codex 봇 발견.
- 사례 2 (PR #737): chat 인계 박스의 GitHub 실제 PR 번호 사전 명시 의무
  누락 — 재검토팀 발견.

거버넌스 안전망이 패턴/프로세스 자체의 한계를 정량 발견하는 자기 진화를
입증한다. 강화 안건 17번 (Standard 12-K 안건 정량 기반)으로 정착한다.
