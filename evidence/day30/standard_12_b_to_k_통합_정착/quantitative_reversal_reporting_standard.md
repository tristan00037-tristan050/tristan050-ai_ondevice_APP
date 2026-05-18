# Standard 12-B — Quantitative Reversal Reporting (신규)

## metadata
- actual_github_pr: 739
- legacy_handoff_label: PR #739+ (chat 인계 박스 표기)
- source_pr: 739
- standard_id: 12-B
- verdict: MEASURED_ONLY

## 본질

자문/인계의 정량 추정이 실측과 반전(reversal)될 때, 그 사실을 숨기지
않고 expected_vs_observed 로 정량 보고하는 것을 표준으로 정착한다
(자문 5차 12 권고).

## 정량 사례

| 사례 | expected (자문/인계 추정) | observed (실측) | 반전 |
|---|---|---|---|
| PR #726 H1 | arbitration 으로 MIXED-A 회복 가능 | avg_evidence_score 1.0 — 회복 불가 | 확정 |
| PR #730 30건 sample | action_unit_mismatch ≥ 8 | A1 = 0 / A3·A4 주류 | 반전 |
| PR #731 30건 sample A3 | A3 = 23 (자문 인계) | A3 = 17 + A5 = 6 (재분류) | 정밀화 |

## 보고 의무

정량 추정 반전 발생 시:
1. `expected` (추정값) 과 `observed` (실측값) 을 나란히 명시.
2. `delta` 와 반전 사유를 서술.
3. 반전이 분류 정밀화 / latent bug / 측정 산식 정정 중 무엇인지 명시.
4. 측정값 임의 조정이 아님을 정직 보고.

## Standard 12 와의 관계

Standard 12 (Honest Reporting Pattern)의 expected_vs_observed 의무를
**정량 반전** 상황으로 구체화한 하위 표준이다. 모든 평가 PR 에 적용.

## 적용

자문 정량 추정과 실측이 다른 경우, 추정을 따르지 않고 실측을 정직 보고
하며 추정의 한계를 기록한다 (PR #730/#731 정합).
