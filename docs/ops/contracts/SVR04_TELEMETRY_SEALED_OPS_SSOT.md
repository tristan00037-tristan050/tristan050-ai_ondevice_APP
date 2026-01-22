# SVR04 Telemetry SEALED-ops SSOT

## 목적
Telemetry Stream(SVR-04/APP-04)이 운영 단계에서 항상 fail-closed로 유지되도록,
GitHub required checks + 증거 링크를 단일 진실원(SSOT)으로 고정한다.

## 운영 강제(Required checks)
- Branch: main
- Required status checks:
  - product-verify-telemetry

## 증거 링크(필수)
- Gate/Impl/Proof PR 링크(최소 2개 이상)
  - PR #149 (telemetry gate): https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/149
  - PR #150 (SVR-04 identifier guard + contamination scan): https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/150
  - PR #151 (APP-04 SDK guard): https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/151
  - PR #152 (HTTP boundary E2E): https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/152

- product-verify-telemetry Actions run 링크(필수)
  - PR #152 (HTTP boundary E2E): https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/21229225851

## 완료 조건(체크리스트)
- [ ] main ruleset에서 product-verify-telemetry가 required check로 설정됨
- [ ] PR 화면에서 product-verify-telemetry가 필수로 표시되고, 실패 시 머지 불가가 보임
- [ ] 위 Actions run 링크가 SSOT에 고정됨

