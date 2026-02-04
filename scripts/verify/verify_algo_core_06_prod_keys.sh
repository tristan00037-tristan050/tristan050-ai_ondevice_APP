#!/usr/bin/env bash
set -euo pipefail

ALGO_CORE_PROD_SSOT_PRESENT_OK=0
ALGO_CORE_PROD_ENV_TEMPLATE_PRESENT_OK=0
ALGO_CORE_KEYGEN_SCRIPT_PRESENT_OK=0
ALGO_CORE_PROD_FAILCLOSED_ENFORCED_OK=0

cleanup(){
  echo "ALGO_CORE_PROD_SSOT_PRESENT_OK=${ALGO_CORE_PROD_SSOT_PRESENT_OK}"
  echo "ALGO_CORE_PROD_ENV_TEMPLATE_PRESENT_OK=${ALGO_CORE_PROD_ENV_TEMPLATE_PRESENT_OK}"
  echo "ALGO_CORE_KEYGEN_SCRIPT_PRESENT_OK=${ALGO_CORE_KEYGEN_SCRIPT_PRESENT_OK}"
  echo "ALGO_CORE_PROD_FAILCLOSED_ENFORCED_OK=${ALGO_CORE_PROD_FAILCLOSED_ENFORCED_OK}"

  if [[ "${ALGO_CORE_PROD_SSOT_PRESENT_OK}" == "1" ]] && \
     [[ "${ALGO_CORE_PROD_ENV_TEMPLATE_PRESENT_OK}" == "1" ]] && \
     [[ "${ALGO_CORE_KEYGEN_SCRIPT_PRESENT_OK}" == "1" ]] && \
     [[ "${ALGO_CORE_PROD_FAILCLOSED_ENFORCED_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

SSOT="docs/ops/contracts/ALGO_CORE_PROD_KEYS_SSOT.md"
ENV_TPL="docs/ops/contracts/ALGO_CORE_PROD_ENV_TEMPLATE.env"
KEYGEN="scripts/ops/algo_core_keygen.sh"
LIB="webcore_appcore_starter_4_17/packages/bff-accounting/src/lib/osAlgoCore.ts"

test -s "$SSOT" && ALGO_CORE_PROD_SSOT_PRESENT_OK=1
test -s "$ENV_TPL" && ALGO_CORE_PROD_ENV_TEMPLATE_PRESENT_OK=1
test -s "$KEYGEN" && ALGO_CORE_KEYGEN_SCRIPT_PRESENT_OK=1

# keygen must run under default node stdin (CommonJS)
grep -nF -- 'require("node:crypto")' "$KEYGEN" >/dev/null || { echo "BLOCK: keygen must use require(\"node:crypto\") for CJS stdin"; exit 1; }
if grep -nF -- 'import crypto from "node:crypto"' "$KEYGEN" >/dev/null; then echo "BLOCK: keygen uses ESM import on stdin"; exit 1; fi

# prod fail-closed가 코드에 박혀 있어야 함(문자열 기반 자산 게이트)
test -s "$LIB"
grep -nF -- "ALGO_CORE_PROD_KEYS_REQUIRED_FAILCLOSED" "$LIB" >/dev/null
grep -nF -- "ALGO_CORE_PROD_KEY_ID_REQUIRED_FAILCLOSED" "$LIB" >/dev/null
grep -nF -- "ALGO_CORE_PROD_KEY_ID_ALLOWLIST_REQUIRED_FAILCLOSED" "$LIB" >/dev/null
grep -nF -- "ALGO_CORE_PROD_KEY_ID_NOT_ALLOWED_FAILCLOSED" "$LIB" >/dev/null

ALGO_CORE_PROD_FAILCLOSED_ENFORCED_OK=1
exit 0
