# Standard 12-H — proxy 측정 vs 권위 측정 분리 (기록→산출물)

## metadata
- actual_github_pr: 739
- legacy_handoff_label: PR #739+ (chat 인계 박스 표기)
- source_pr: 739
- standard_id: 12-H
- verdict: MEASURED_ONLY

## 본질

deterministic simulation 등으로 산출한 **proxy 측정값**은 권위 측정값이
아니다. 둘을 명확히 분리 기록하고, proxy 를 권위 판정에 사용하지 않는다
(자문 6차 M-10 정합).

## 정량 근거 (PR #733 + PR #737)

- PR #733: manual_suggestion_precision proxy (strict 0.4688 / lenient
  0.6562) — deterministic reviewer-simulation. Cohen's κ proxy 0.6735.
- 권위 측정은 정식 Internal Alpha user feedback (option C) — PR #737
  수집 계획.
- proxy 는 Controlled Beta 진입 판정에 사용 불가 (M-10).

## 표준

1. 측정값은 `proxy` / `authoritative` 를 명시한다.
2. proxy 측정은 산출 방법(simulation / 추정)을 정직 기록하고 confidence
   를 낮게 표기한다.
3. proxy 값을 게이트/진입 판정의 권위 근거로 사용하지 않는다.
4. 권위 측정 path (option C 등)를 분명히 안내한다.

## Standard 12-H 적용

simulation/추정 기반 측정을 보고하는 모든 PR 은 proxy 임을 명시하고,
권위 측정 전 진입/승격 결정을 내리지 않는다. expected_vs_observed 의
confidence 필드로 한계를 정직 보고한다.
