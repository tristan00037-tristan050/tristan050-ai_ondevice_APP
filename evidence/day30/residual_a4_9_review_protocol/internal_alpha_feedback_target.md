# Internal Alpha Feedback Target (자문 6차 M-5)

## metadata
- actual_github_pr: 738
- legacy_handoff_label: PR #738+ (chat 인계 박스 표기)
- source_pr: 738
- branch: Residual-A4-9-Review-Protocol
- verdict: MEASURED_ONLY

## 목적

잔여 A4 9건 유형을 Internal Alpha feedback 의 명시적 target 으로 지정한다
(자문 6차 M-5 — 옵션 D 1순위: Internal Alpha feedback 후 사용자 가치 판정).

## feedback target 유형

| 표면형 | 건수 | feedback 질문 |
|---|---|---|
| polite_request_surface_form | 7 | '부탁드립니다' 진술의 suggestion 이 유용한가 |
| intent_to_report_surface_form | 2 | '보고드리려고 합니다' 진술의 suggestion 이 유용한가 |

## 4 카테고리 수집 (PR #737 권위 측정 protocol)

- `useful` / `irrelevant` / `unsafe` / `needs_edit`.
- PR #737 의 sample stratum 구성에서 잔여 A4 9건 유형은
  `residual_a4_ambiguous_request_report` stratum (권장 150건 중 30건)에
  포함된다.
- 수집은 PR #733 계측 인프라 (digest 저장 / 외부 전송 0 / auto_apply OFF).

## 사용자 가치 판정 protocol

1. Internal Alpha 사용자가 잔여 A4 유형 suggestion 에 4 카테고리 평가.
2. reviewer 가 동일 sample 을 평가 (`reviewer_guide.md` 정합).
3. `useful` 비율이 높으면 → manual suggestion 가치 확인 → metric
   contract v2.1.0 후보 진행.
4. `unsafe` 비율이 높으면 → semantic-aware guard v0 candidate (post-hoc
   warning) 진행.

## 정직 보고

본 PR 은 target 지정만 한다. 실제 feedback 수집·판정은 정식 Internal
Alpha 배포 후 (PR #737 계획 정합). 권위 측정 전 처리 방향을 확정하지
않는다.
