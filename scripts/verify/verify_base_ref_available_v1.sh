#!/usr/bin/env bash
set -euo pipefail

BASE_REF_OK=0
MERGE_BASE_OK=0
finish() {
  echo "BASE_REF_OK=${BASE_REF_OK}"
  echo "MERGE_BASE_OK=${MERGE_BASE_OK}"
}
trap finish EXIT

if ! git rev-parse --verify origin/main >/dev/null 2>&1; then
  echo "ERROR_CODE=BASE_REF_UNAVAILABLE"
  exit 1
fi
BASE_REF_OK=1

if ! git merge-base origin/main HEAD >/dev/null 2>&1; then
  echo "ERROR_CODE=MERGE_BASE_UNAVAILABLE"
  exit 1
fi
MERGE_BASE_OK=1
exit 0
