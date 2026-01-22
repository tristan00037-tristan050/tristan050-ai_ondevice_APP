# SVR05 Attestation SEALED-ops SSOT

## 목적
Stream A(SVR-05/APP-03 Attestation)가 운영 단계에서 항상 fail-closed로 유지되도록,
GitHub required checks + 증거 링크를 단일 진실원(SSOT)으로 고정한다.

## 운영 강제(Required checks)
- Branch: main
- Required status checks:
  - product-verify-attestation

## 구현(레포 경로)
- verify script:
  - webcore_appcore_starter_4_17/scripts/verify/verify_svr05_attestation.sh

## 봉인 커맨드(출력 기반)
- 오염 스캔(0건이어야 함)
  - rg -n "OK=1" webcore_appcore_starter_4_17/backend/attestation/tests || true

- verify + exit (PASS에서만 키=1, EXIT=0)
  - bash webcore_appcore_starter_4_17/scripts/verify/verify_svr05_attestation.sh ; echo EXIT=$?

PASS requires:
- ATTEST_VERIFY_FAILCLOSED_OK=1
- ATTEST_ALLOW_OK=1
- ATTEST_BLOCK_OK=1
- EXIT=0

## 증거 링크(필수)
- product-verify-attestation Actions run 링크(필수)
  - (여기에 "대표 run 1개" URL을 붙여넣기)

## 완료 조건(체크리스트)
- [ ] main ruleset/branch protection에서 product-verify-attestation가 required check로 설정됨
- [ ] PR 화면에서 product-verify-attestation가 필수로 표시되고, 실패 시 머지 불가가 보임
- [ ] Actions run 링크가 SSOT에 고정됨

