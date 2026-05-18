# Text-only Guard 한계 정량 확정 (자문 6차 M-1)

## metadata
- actual_github_pr: 738
- legacy_handoff_label: PR #738+ (chat 인계 박스 표기)
- source_pr: 738
- branch: Residual-A4-9-Review-Protocol
- verdict: MEASURED_ONLY

## text-only guard 추가 강화 금지 (자문 6차 M-1)

자문 6차 M-1 — 잔여 A4 9건에 대한 text-only guard 추가 차단은 **금지**.
본 PR 은 text-only guard 를 추가 강화하지 않으며, 한계를 정량 확정한다.

## text-only guard 한계 정량 (PR #732 정직 보고 정합)

PR #732 B-2G 는 A4 29건 중 20건을 차단했고, 잔여 9건은 차단하지 못했다.
잔여 9건의 한계 원인:

| 표면형 | 건수 | text-only 분리 불가 원인 |
|---|---|---|
| polite_request_surface_form | 7 | '부탁드립니다' = 정상 요청(gold≥1) 및 A5 와 표면 동일 |
| intent_to_report_surface_form | 2 | '보고드리려고 합니다' = A5 card1_100078 과 표면 동일 |

차단 강행 시:
- '부탁' 형 차단 → 정상 요청(비-MIXED-A) 의 action 손실 → strict_action_f1
  하락 (≥ 0.6182 금지선 위반).
- '보고드리려고' 형 차단 → A5 card1_100078 (gold≥1) 의 gold action 손실
  (A5 영향 0 금지선 위반).

→ text-only guard 로는 잔여 9건을 안전 분리할 수 없음을 **정량 확정**.

## 후속 방향

text-only guard 가 아니라:
- Internal Alpha feedback (사용자 가치 실측) — `internal_alpha_feedback_target.md`.
- semantic-aware guard v0 (post-hoc warning, 차단 아님) —
  `semantic_aware_guard_v0_candidate.md`.

## 정직 보고

본 한계 확정은 PR #732 의 정직 보고를 자문 6차 M-1 정합으로 강화한 것.
text-only guard 의 추가 강화 시도는 금지되며, 잔여 9건은 평가 protocol
분리 + Internal Alpha feedback 으로 처리한다.
