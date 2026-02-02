#!/usr/bin/env bash
set -euo pipefail

ONPREM_PROOF_LATEST_FRESH_OK=0

cleanup() {
  echo "ONPREM_PROOF_LATEST_FRESH_OK=${ONPREM_PROOF_LATEST_FRESH_OK}"
  if [[ "${ONPREM_PROOF_LATEST_FRESH_OK}" == "1" ]]; then exit 0; fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY="docs/ops/contracts/PROOF_FRESHNESS_POLICY_V1.md"
LATEST="docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md"

test -s "$POLICY" || { echo "BLOCK: missing $POLICY"; exit 1; }
test -s "$LATEST" || { echo "BLOCK: missing/empty $LATEST"; exit 1; }

MAX_AGE_DAYS="$(grep -nE '^MAX_AGE_DAYS=' "$POLICY" | tail -n 1 | cut -d= -f2 | tr -d '[:space:]')"
[[ -n "$MAX_AGE_DAYS" ]] || { echo "BLOCK: MAX_AGE_DAYS missing"; exit 1; }

# LATEST에서 날짜(YYYY-MM-DD) 추출 → 최신 날짜 1개 선택
LAST_DATE="$(grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' "$LATEST" | sort | tail -n 1)"
[[ -n "$LAST_DATE" ]] || { echo "BLOCK: no date (YYYY-MM-DD) found in LATEST"; exit 1; }

# 오늘(UTC) 기준으로 age 계산
TODAY="$(date -u +%F)"
AGE_DAYS="$(( ( $(date -u -d "$TODAY" +%s) - $(date -u -d "$LAST_DATE" +%s) ) / 86400 ))"

if [[ "$AGE_DAYS" -lt 0 ]]; then
  echo "BLOCK: last_date is in the future: $LAST_DATE"
  exit 1
fi

if [[ "$AGE_DAYS" -gt "$MAX_AGE_DAYS" ]]; then
  echo "BLOCK: proof too old (age_days=$AGE_DAYS > max_age_days=$MAX_AGE_DAYS), last_date=$LAST_DATE"
  exit 1
fi

ONPREM_PROOF_LATEST_FRESH_OK=1

