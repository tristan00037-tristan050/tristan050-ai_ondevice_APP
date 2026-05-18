# Standard 9 본질적 강화 완성

## metadata
- actual_github_pr: 739
- legacy_handoff_label: PR #739+ (chat 인계 박스 표기)
- source_pr: 739
- verdict: MEASURED_ONLY

## Standard 9 (Dataset Integrity Fail-Closed) 강화 경로

| 단계 | PR | 강화 내용 |
|---|---|---|
| 정착 | #728 | coverage_report 12 필드 + fail_class 분류 |
| 강화 1 | #730 | `detect_duplicates()` — duplicate sample_id fail-closed |
| 강화 2 | #734 | `compute_coverage()` — missing samples fail-closed (latent gap 정정) |

## 본질적 강화 완성 — duplicate + missing 동시 차단

`compute_coverage(mixed_id_list, dataset_ids, pred_id_list)` 는 다음을
모두 fail-closed 한다:

- **duplicate** — source / prediction sample_id 중복 (`detect_duplicates`).
- **missing** — required sample 이 dataset / predictions 에서 누락.
- **measured vs expected 정량 비교** — hardcoded 금지.

fail_class: `SOURCE_SAMPLE_ID_DUPLICATE` / `FULL_EVAL_COVERAGE_MISMATCH`
(duplicate or missing).

## 통합 명세

모든 평가 PR 의 dataset integrity gate 는 `compute_coverage()` 를 통해
duplicate + missing 을 동시 검증한다. coverage_report 는 12 표준 필드 +
확장 필드 (source/prediction count·unique, missing_from_dataset·predictions)
를 갖는다.

## Standard 12-J 와의 관계

Standard 12-J (dataset integrity coverage_mismatch)는 본 강화의 표준화
사례다 — `dataset_integrity_coverage_audit.md` (PR #734) 참조. Standard 9
본질적 강화는 12-J 로 표준 문서화되었고, 본 통합 정착으로 완성된다.

## 정직 보고

본 강화는 PR #730 패턴의 latent gap(missing samples)을 Codex 봇이 발견
(거버넌스 자기 진화 사례 1)하여 PR #734 에서 정정한 결과다. 측정값
임의 조정이 아니며 dataset 무결성 검증의 완전성을 높인 것이다.
