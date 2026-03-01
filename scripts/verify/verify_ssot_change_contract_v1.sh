#!/usr/bin/env bash
set -euo pipefail

SSOT_CHANGE_CONTRACT_V1_OK=0
finish(){ echo "SSOT_CHANGE_CONTRACT_V1_OK=${SSOT_CHANGE_CONTRACT_V1_OK}"; }
trap finish EXIT

# 감시 대상 SSOT(최소 세트, add-only 확장)
SSOT_FILES=(
  "docs/ops/contracts/OUTPUT_ROOT_SSOT_V1.txt"
  "docs/ops/contracts/EXEC_MODE_SCHEMA_V1.json"
)

BASE_REF="${SSOT_CONTRACT_BASE_REF:-origin/main}"
git rev-parse --verify "$BASE_REF" >/dev/null 2>&1 || { echo "ERROR_CODE=BASE_REF_MISSING"; exit 1; }

changed=0
for f in "${SSOT_FILES[@]}"; do
  if git diff --name-only "$BASE_REF"...HEAD -- "$f" | grep -q .; then
    changed=1
    break
  fi
done

# SSOT 미변경이면 영향 0 (PASS)
if [ "$changed" = "0" ]; then
  SSOT_CHANGE_CONTRACT_V1_OK=1
  exit 0
fi

# SSOT 변경 시: 필수 가드가 repo contracts 체인에 존재해야 함(동반 소비/검증 강제)
required_guards=(
  "output root ssot v1"
  "exec-mode schema ssot consumed v1"
)

missing=0
for g in "${required_guards[@]}"; do
  if ! grep -Fq "run_guard \"${g}\"" scripts/verify/verify_repo_contracts.sh; then
    echo "ERROR_CODE=MISSING_REQUIRED_GUARD"
    echo "MISSING_GUARD=${g}"
    missing=1
  fi
done

[ "$missing" = "0" ] || exit 1

SSOT_CHANGE_CONTRACT_V1_OK=1
exit 0
