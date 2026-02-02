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

# 오늘(UTC) 기준으로 age 계산 (POSIX 호환: Node.js 사용)
AGE_DAYS="$(node -e "
const last = new Date('${LAST_DATE}T00:00:00Z');
const today = new Date();
const ageMs = today - last;
const ageDays = Math.floor(ageMs / (1000 * 60 * 60 * 24));
if (ageDays < 0) {
  console.error('BLOCK: last_date is in the future: ${LAST_DATE}');
  process.exit(1);
}
console.log(ageDays);
")"

if [[ -z "$AGE_DAYS" ]] || ! [[ "$AGE_DAYS" =~ ^[0-9]+$ ]]; then
  echo "BLOCK: failed to calculate age_days"
  exit 1
fi

if [[ "$AGE_DAYS" -gt "$MAX_AGE_DAYS" ]]; then
  echo "BLOCK: proof too old (age_days=$AGE_DAYS > max_age_days=$MAX_AGE_DAYS), last_date=$LAST_DATE"
  exit 1
fi

ONPREM_PROOF_LATEST_FRESH_OK=1

