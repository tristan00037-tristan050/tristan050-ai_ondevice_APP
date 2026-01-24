#!/usr/bin/env bash
set -euo pipefail

STORAGE_REPORT_KEYS_PRESENT_OK=0
cleanup() { echo "STORAGE_REPORT_KEYS_PRESENT_OK=${STORAGE_REPORT_KEYS_PRESENT_OK}"; }
trap cleanup EXIT

OUT="$(bash webcore_appcore_starter_4_17/scripts/ops/svr03_storage_report.sh 2>&1 || true)"

need() {
  echo "$OUT" | grep -q "$1" || { echo "FAIL: missing $1"; echo "$OUT"; exit 1; }
}

need "LOCK_TIMEOUT_COUNT_24H="
need "PERSIST_CORRUPTED_COUNT_24H="
need "AUDIT_ROTATE_COUNT_24H="
need "AUDIT_RETENTION_DELETES_24H="

STORAGE_REPORT_KEYS_PRESENT_OK=1
exit 0

