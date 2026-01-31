#!/usr/bin/env bash
set -euo pipefail

WEB_E2E_EXPORT_TWO_STEP_OK=0
WEB_E2E_EXPORT_AUDITV2_OK=0
EXPORT_APPROVE_IDEMPOTENT_OK=0
EXPORT_APPROVE_AUDIT_ID_RETURNED_OK=0

cleanup() {
  echo "WEB_E2E_EXPORT_TWO_STEP_OK=${WEB_E2E_EXPORT_TWO_STEP_OK}"
  echo "WEB_E2E_EXPORT_AUDITV2_OK=${WEB_E2E_EXPORT_AUDITV2_OK}"
  echo "EXPORT_APPROVE_IDEMPOTENT_OK=${EXPORT_APPROVE_IDEMPOTENT_OK}"
  echo "EXPORT_APPROVE_AUDIT_ID_RETURNED_OK=${EXPORT_APPROVE_AUDIT_ID_RETURNED_OK}"
}
trap cleanup EXIT

E2E_DIR="webcore_appcore_starter_4_17/scripts/web_e2e"
test -s "${E2E_DIR}/package-lock.json" || { echo "BLOCK: package-lock.json missing (npm ci only)"; exit 1; }

npm --prefix "${E2E_DIR}" ci
npx --prefix "${E2E_DIR}" playwright install chromium

node "${E2E_DIR}/run_export_audit_e2e.mjs"

WEB_E2E_EXPORT_TWO_STEP_OK=1
WEB_E2E_EXPORT_AUDITV2_OK=1
EXPORT_APPROVE_IDEMPOTENT_OK=1
EXPORT_APPROVE_AUDIT_ID_RETURNED_OK=1

