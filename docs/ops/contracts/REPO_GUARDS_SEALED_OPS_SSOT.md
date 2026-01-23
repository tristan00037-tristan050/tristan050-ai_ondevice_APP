# Repo Guards SEALED-ops SSOT

## 목적
repo-wide 상위 가드(오염/merge_group 커버리지/SSOT placeholder)가
운영 단계에서도 항상 fail-closed로 유지되도록 required check + 증거 링크를 단일 진실원(SSOT)으로 고정한다.

## 운영 강제(Required checks)
- Branch: main
- Required status checks:
  - product-verify-repo-guards

## 증거 링크(필수)
- PR 링크 (Repo Guards 도입)
  - (여기에 P0-3 PR 링크를 붙여 넣기)

- product-verify-repo-guards Actions run 링크(필수)
  - (여기에 Actions run URL을 붙여 넣기)

- Ruleset/Branch protection evidence(필수)
  - docs/ops/evidence/2026-01-23_ruleset_required_checks_repo_guards.md

## 봉인 커맨드(출력 기반)
- repo guards verify + exit (PASS에서만 키=1, EXIT=0)
  - bash scripts/verify/verify_repo_guards.sh ; echo EXIT=$?

PASS requires:
- OK_CONTAMINATION_GUARD_OK=1
- REQUIRED_CHECK_MERGE_GROUP_COVERAGE_OK=1
- SSOT_PLACEHOLDER_GUARD_OK=1
- EXIT=0

## 완료 조건(체크리스트)
- [ ] main ruleset/branch protection에서 product-verify-repo-guards가 required check로 설정됨
- [ ] PR 화면에서 product-verify-repo-guards가 필수로 표시되고, 실패 시 머지 불가가 보임
- [ ] Actions run 링크가 SSOT에 고정됨
- [ ] evidence 파일에 설정 근거가 텍스트로 고정됨

