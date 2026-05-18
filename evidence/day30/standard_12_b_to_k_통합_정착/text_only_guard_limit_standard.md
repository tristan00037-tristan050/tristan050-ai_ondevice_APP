# Standard 12-E — text-only Guard 한계 정량 보증 (기록→산출물)

## metadata
- actual_github_pr: 739
- legacy_handoff_label: PR #739+ (chat 인계 박스 표기)
- source_pr: 739
- standard_id: 12-E
- verdict: MEASURED_ONLY

## 본질

text-only post-processing guard 는 표면형이 동일한 케이스를 안전 분리할
수 없다. 그 한계를 정량 보증하고, 한계 초과 차단을 금지한다 (자문 6차
M-1 정합).

## 정량 근거 (PR #732 + PR #738)

- PR #732 B-2G: A4 29건 중 20건 차단, 잔여 9건 차단 불가.
- 잔여 9건 한계 원인:
  - polite_request_surface_form 7건 — '부탁드립니다' 가 정상 요청
    (gold≥1) / A5 와 표면 동일.
  - intent_to_report_surface_form 2건 — '보고드리려고 합니다' 가 A5
    card1_100078 과 표면 동일.
- 차단 강행 시 strict_action_f1 하락 / A5 영향 0 금지선 위반.

## 표준

1. text-only guard 는 표면형 ambiguous case 를 차단하지 않는다.
2. guard 한계는 정량 보증한다 (차단 건수 / 잔여 건수 / 한계 원인).
3. 한계 초과 케이스는 평가 protocol 분리 + Internal Alpha feedback 으로
   처리한다 (PR #738 정합).
4. text-only guard 추가 강화는 금지 (자문 6차 M-1).

## Standard 12-E 적용

post-processing guard 를 도입하는 모든 PR 은 guard 한계를 정량 보고하고,
표면형 동일 케이스를 차단 대상에서 제외한다.
