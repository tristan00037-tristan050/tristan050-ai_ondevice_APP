# Standard 12-K — PR 번호 정합성 메타데이터 무결성 (통합 명세)

## metadata
- actual_github_pr: 739
- legacy_handoff_label: PR #739+ (chat 인계 박스 표기)
- source_pr: 739
- standard_id: 12-K
- verdict: MEASURED_ONLY

## 본질

PR / evidence 의 메타데이터에서 GitHub 실제 PR 번호와 chat 인계 박스의
잠정 표기를 분리 기록한다. PR #737 의 `metadata_integrity_audit.md`
정착분을 통합 표준으로 보강한다.

## 정량 근거 (PR #737)

chat 인계 박스가 'PR #735+' 표기를 사용했으나 실제 GitHub PR 은 #737.
evidence 의 `source_pr` 가 735 로 고정되어 불일치 — 메타데이터 정합 결함.
거버넌스 안전망 자기 진화 사례 2호.

## 표준 — 필수 메타데이터 필드

| 필드 | 의미 |
|---|---|
| `actual_github_pr` | `gh pr create` 응답의 실제 PR 번호 |
| `legacy_handoff_label` | chat 인계 박스의 잠정 표기 |
| `source_pr` | actual_github_pr 와 일치 |

## 인계 박스 작성 표준

1. evidence script 는 `ACTUAL_GITHUB_PR` 상수를 중앙 관리한다.
2. `gh pr create` 응답 번호가 잠정 표기와 다르면 `actual_github_pr` 를
   실제 번호로 정정하고 metadata correction cycle 을 수행한다.
3. PR title / body 는 actual_github_pr 기준으로 작성한다.
4. evidence 의 `source_pr` 는 actual_github_pr 와 항상 일치시킨다.

## PR #738 정합 검증

PR #738 은 본 표준 적용 — 인계 박스 표기 'PR #738+' 와 실제 GitHub PR
번호 #738 이 일치, metadata correction cycle 불필요 (표준 정착 효과 입증).

## Standard 12-K 적용

모든 향후 인계 박스 + PR 생성은 본 표준을 의무 적용한다. 메타데이터
무결성은 거버넌스 안전망 14차원의 구성 요소다.
