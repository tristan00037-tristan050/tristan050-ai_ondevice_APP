# Reusable Helpers 누적 Audit

## metadata
- actual_github_pr: 739
- legacy_handoff_label: PR #739+ (chat 인계 박스 표기)
- source_pr: 739
- verdict: MEASURED_ONLY

## 재사용 helper 3개

| helper | origin | signature |
|---|---|---|
| `detect_duplicates` | PR #730 | `detect_duplicates(id_list) -> (dups, excess)` |
| `compute_readiness` | PR #733 | `compute_readiness(safety, ...) -> dict` |
| `compute_coverage` | PR #734 | `compute_coverage(mixed_id_list, dataset_ids, pred_id_list) -> dict` |

## detect_duplicates (PR #730)

sample_id 리스트의 중복을 raw 단계에서 검출. dict comprehension collapse
이전 호출 — Standard 9 / 12-J 정합. PR #731~#739 가 import 재사용.

## compute_readiness (PR #733)

readiness gate 를 실제 metric 에서 산출 (hardcoded literal 금지) —
Standard 12-I 정합. PR #734 가 Controlled Beta 정량 결정에 재사용.

## compute_coverage (PR #734)

duplicate + missing 동시 fail-closed — Standard 9 본질적 강화 / 12-J
정합. PR #735·#738·#739 가 dataset integrity 무결성 확인에 재사용.

## 재사용 가이드 (향후 PR)

- 평가/계획/통합 PR 의 dataset integrity gate 는 `compute_coverage()` 를
  import 재사용한다 (재구현 금지 — 단일 정의 원칙).
- readiness gate 가 필요한 PR 은 `compute_readiness()` 를 재사용한다.
- 중복 검출은 `detect_duplicates()` 를 재사용한다.
- import 경로는 각 helper 의 origin script (pr730/pr733/pr734)를 따른다.

## 정직 보고

helper 재사용은 코드 중복을 줄이고 정합성을 보장한다. 본 audit 은 helper
3개의 누적을 표준 문서화한 것이며, 새 helper 추가나 측정 변경은 없다.
