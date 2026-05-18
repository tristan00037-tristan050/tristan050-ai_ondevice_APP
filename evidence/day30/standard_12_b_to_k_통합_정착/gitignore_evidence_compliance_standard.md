# Standard 12-G — .gitignore Evidence 정합 검증 (기록→산출물)

## metadata
- actual_github_pr: 739
- legacy_handoff_label: PR #739+ (chat 인계 박스 표기)
- source_pr: 739
- standard_id: 12-G
- verdict: MEASURED_ONLY

## 본질

evidence 산출물이 `.gitignore` 패턴에 의해 의도치 않게 추적 제외되는
것을 방지한다. evidence 는 sentinel 의존성을 가지므로 반드시 추적되어야
한다.

## 정량 근거 (PR #733)

- `.gitignore` 의 `*_result.json` 패턴이 `reviewer_feedback_result.json` /
  `synthetic_feedback_simulation_result.json` (자문 5차 산출물)을 차단.
- `git status` 가 `??` 로 표시하지 않아 누락이 silent.
- 정정: `git add -f` 강제 추가 (기존 11개 `_result.json` evidence 추적
  선례 정합).

## 표준

1. PR 커밋 후 evidence 디렉토리의 모든 산출물이 `git ls-files` 에
   포함되는지 검증한다.
2. `.gitignore` 패턴에 걸린 evidence 는 `git add -f` 로 강제 추가하고,
   그 사실을 커밋 메시지에 기록한다.
3. evidence 파일명은 가능하면 `.gitignore` 패턴과 충돌하지 않게 짓는다.
4. sentinel 이 의존하는 evidence 는 누락 시 sentinel 실패로 드러나므로,
   커밋 전 sentinel 을 fresh checkout 기준으로 점검한다.

## Standard 12-G 적용

모든 평가 PR 은 커밋 후 evidence 추적 누락 0건을 검증한다. 누락 발견 시
force-add + 커밋 메시지 기록.
