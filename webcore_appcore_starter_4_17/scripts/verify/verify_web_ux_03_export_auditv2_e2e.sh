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

# Check dependencies exist (workflow must install)
test -d "${E2E_DIR}/node_modules" || { echo "BLOCK: node_modules missing (workflow must run npm ci)"; exit 1; }
test -d "${PLAYWRIGHT_BROWSERS_PATH:-${HOME}/.cache/ms-playwright}" || { echo "BLOCK: playwright browsers missing (workflow must install)"; exit 1; }

node "${E2E_DIR}/run_export_audit_e2e.mjs"

WEB_E2E_EXPORT_TWO_STEP_OK=1
WEB_E2E_EXPORT_AUDITV2_OK=1
EXPORT_APPROVE_IDEMPOTENT_OK=1
EXPORT_APPROVE_AUDIT_ID_RETURNED_OK=1

