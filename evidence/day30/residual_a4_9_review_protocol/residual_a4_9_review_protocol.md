# Residual A4 9 Review Protocol (자문 6차 §13 PR B)

## metadata
- actual_github_pr: 738
- legacy_handoff_label: PR #738+ (chat 인계 박스 표기)
- source_pr: 738
- branch: Residual-A4-9-Review-Protocol
- verdict: MEASURED_ONLY

## 목적

PR #732 B-2G 가 안전 차단하지 못한 잔여 A4 9건을, **직접 수정하지 않고**
평가 protocol 로 분리한다. 자문 6차 M-5(옵션 D 1순위) — Internal Alpha
feedback 후 사용자 가치 판정. 자문 6차 §13 PR B 정합.

## 잔여 A4 9건 (표면형 ambiguous over-extraction cases — M-2)

| 표면형 | 건수 | 예 |
|---|---|---|
| polite_request_surface_form ('부탁드립니다/부탁드려요') | 7 | 보고서 검토 부탁드립니다 |
| intent_to_report_surface_form ('보고드리려고 합니다') | 2 | 결과 정리 후 보고드리려고 합니다 |

자문 6차 M-2 — 이들은 gold 가 REPORT/0-action 이나 표면형이 정상 요청
(gold≥1) 및 A5 케이스와 구분 불가한 **surface-form ambiguous
over-extraction cases** 다.

## 처리 방향 (자문 6차 M-5 — 옵션 D 1순위)

1. **직접 수정 0** — gold label 수정 절대 금지 (M-3). text-only guard
   추가 강화 0 (M-1).
2. **평가 protocol 분리** — strict layer 에서 FP 로 유지,
   `evaluation_protocol_separation.md` 의 gold/contract review path.
3. **Internal Alpha feedback target 지정** — `internal_alpha_feedback_target.md`,
   4 카테고리 수집 (PR #737 권위 측정 protocol).
4. **사용자 가치 판정 후 분기** — feedback 결과로 옵션 B(metric contract
   review) 진행.

## 후속 산출물

- `evaluation_protocol_separation.md` — 평가 protocol 분리.
- `internal_alpha_feedback_target.md` — feedback target.
- `semantic_aware_guard_v0_candidate.md` — guard v0 candidate (post-hoc).
- `metric_contract_v2_1_0_candidate.md` — v2.1.0 후보 (즉시 bump 0).
- `text_only_guard_한계_정량_확정.md` — text-only guard 한계 확정.

## 금지선

gold/label 수정 0 / text-only guard 추가 강화 0 / metric contract
v2.1.0 즉시 bump 0 / prompt·model 변경 0 / PROCEED 금지.
