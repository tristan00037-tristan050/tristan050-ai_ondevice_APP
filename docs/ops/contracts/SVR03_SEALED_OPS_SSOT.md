# SVR-03 SEALED-ops — SSOT

## 목적
Model Registry Stream(SVR-03)이 운영 단계에서 항상 fail-closed로 유지되도록,
GitHub required checks + 증거 링크를 단일 진실원(SSOT)으로 고정한다.

## 운영 강제(Required checks)
- Branch: main
- Required status checks:
  - product-verify-model-registry

## PR (evidence)
- #164 canonical payload + reason_code v1
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/164
- #165 signature required (fail-closed) for artifact register
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/165
- #166 tamper tests + verify sealing tightened
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/166
- #175 canonicalization 공통화 (P0-5)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/175
- #176 delivery/apply/rollback 서명 강제 (P0-6)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/176
- #177 key rotation/revoke (P0-7)
  - https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/pull/177

## Actions Run (product-verify-model-registry)
- 최신 run: https://github.com/tristan00037-tristan050/tristan050-ai_ondevice_APP/actions/runs/21238929913
- (PR #177 이후 최신 run URL로 업데이트 필요)

## Ruleset evidence
- docs/ops/evidence/2026-01-23_ruleset_required_checks_svr03_model_registry.md

## 봉인 커맨드(출력 기반)
- 오염 스캔(0건이어야 함)
  - rg -n "OK=1" webcore_appcore_starter_4_17/backend/model_registry/tests || true

- verify + exit (PASS에서만 키=1, EXIT=0)
  - bash webcore_appcore_starter_4_17/scripts/verify/verify_svr03_model_registry.sh ; echo EXIT=$?

PASS requires:
- MODEL_UPLOAD_SIGN_VERIFY_OK=1
- MODEL_DELIVERY_SIGNATURE_REQUIRED_OK=1
- MODEL_APPLY_FAILCLOSED_OK=1
- MODEL_ROLLBACK_OK=1
- EXIT=0

## 완료 조건(체크리스트)
- [x] main ruleset/branch protection에서 product-verify-model-registry가 required check로 설정됨
- [x] PR 화면에서 product-verify-model-registry가 필수로 표시되고, 실패 시 머지 불가가 보임
- [x] P0-5~P0-7 PR 링크가 SSOT에 고정됨
- [x] Ruleset evidence 파일이 생성되고 SSOT에 링크됨
