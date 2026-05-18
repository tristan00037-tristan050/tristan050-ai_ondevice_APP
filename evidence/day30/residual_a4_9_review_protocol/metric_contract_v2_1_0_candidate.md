# Metric Contract v2.1.0 Candidate (자문 6차 M-8)

## metadata
- actual_github_pr: 738
- legacy_handoff_label: PR #738+ (chat 인계 박스 표기)
- source_pr: 738
- branch: Residual-A4-9-Review-Protocol
- verdict: MEASURED_ONLY

## v2.1.0 즉시 bump 0 (자문 6차 M-8 절대 준수)

본 PR 은 metric contract version 을 v2.1.0 으로 **즉시 bump 하지 않는다**
(자문 6차 M-8). 현 contract 는 **v2.0.0 유지**. 본 문서는 v2.1.0 **후보
안건 명세만** 정착한다.

## v2.1.0 후보 안건 — Layer 2 manual suggestion metric 강화

| candidate metric | 정의 |
|---|---|
| `manual_suggestion_precision` | useful / (useful+irrelevant+unsafe+needs_edit) |
| `suggestion_usefulness_rate` | useful 비율 |
| `unsafe_suggestion_rate` | unsafe 비율 |
| `edit_required_rate` | needs_edit 비율 |

Layer 1 (`strict_action_f1`)은 불변 — v2.1.0 은 Layer 2 보조 지표
강화에 한정.

## v2.1.0 bump 조건 (정량)

다음 중 하나 충족 시 v2.1.0 bump 를 별도 PR 로 검토:

1. `manual_suggestion_precision` **권위 측정** ≥ 0.80, 또는
2. A3/A4 잔여 케이스에서 사용자 가치 분리가 **반복 확인**, 또는
3. manual suggestion layer 가 `strict_action_f1` 과 분리되어 **제품 판단**
   이 필요해진 경우.

SemVer: v2.0.0 → v2.1.0 (MINOR — Layer 2 보조 지표 추가, Layer 1 불변).

## 정직 보고 (자문 6차 M-8)

본 PR 은 후보 안건만 명세하며 contract version 을 변경하지 않는다.
권위 측정(option C) 전 v2.1.0 bump 는 금지 — bump 조건 충족을 정량
확인한 후 별도 PR.
