# WEB Console SEALED-ops SSOT

## 목적
Stream C(Web Console)가 운영 단계에서 항상 fail-closed로 유지되도록,
required check + 증거 링크를 단일 진실원(SSOT)으로 고정한다.

## 운영 강제(Required checks)
- Branch: main
- Required status checks:
  - product-verify-web-console

## 증거 링크(필수)
- Gate/Impl PR 링크
  - PR #155 (오염 제거)
  - PR #156 (verify_web_console 게이트)
  - PR #157 (required check workflow)

- product-verify-web-console Actions run 링크(필수)
  - (여기에 "대표 run 1개" URL을 붙여넣기)

## 봉인 커맨드(출력 기반)
- 오염 스캔(0건이어야 함)
  - rg -n "OK=1" webcore_appcore_starter_4_17/web_console/admin/tests || true

- verify + exit (PASS에서만 키=1, EXIT=0)
  - bash webcore_appcore_starter_4_17/scripts/verify/verify_web_console.sh ; echo EXIT=$?

PASS requires:
- CONSOLE_ONBOARDING_DONE_OK=1
- RBAC_UI_ENFORCE_OK=1
- EXIT=0

## 완료 조건(체크리스트)
- [ ] main ruleset/branch protection에서 product-verify-web-console가 required check로 설정됨
- [ ] PR 화면에서 product-verify-web-console가 필수로 표시되고, 실패 시 머지 불가가 보임
- [ ] Actions run 링크가 SSOT에 고정됨

