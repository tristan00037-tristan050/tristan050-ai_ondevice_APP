#!/usr/bin/env bash
set -euo pipefail

SSOT_REGISTRY_STUB_BURNDOWN_OK=0
finish() {
  echo "SSOT_REGISTRY_STUB_BURNDOWN_OK=${SSOT_REGISTRY_STUB_BURNDOWN_OK}"
  [ -n "${SSOT_REGISTRY_STUB_COUNT_BASE:-}" ] && echo "SSOT_REGISTRY_STUB_COUNT_BASE=${SSOT_REGISTRY_STUB_COUNT_BASE}"
  [ -n "${SSOT_REGISTRY_STUB_COUNT_HEAD:-}" ] && echo "SSOT_REGISTRY_STUB_COUNT_HEAD=${SSOT_REGISTRY_STUB_COUNT_HEAD}"
}
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

REGISTRY="docs/ops/contracts/SSOT_REGISTRY_V1.txt"
BUDGET="docs/ops/contracts/SSOT_REGISTRY_STUB_BUDGET_V1.txt"
BASE_REF="${SSOT_STUB_BURNDOWN_BASE_REF:-origin/main}"

git rev-parse --verify "$BASE_REF" >/dev/null 2>&1 || { echo "ERROR_CODE=BASE_REF_UNAVAILABLE"; exit 1; }
test -f "$BUDGET" || { echo "ERROR_CODE=BUDGET_MISSING"; exit 1; }
grep -q '^SSOT_REGISTRY_STUB_BUDGET_V1_TOKEN=1' "$BUDGET" || { echo "ERROR_CODE=BUDGET_INVALID"; exit 1; }

stub_max=$(grep -E '^STUB_MAX=' "$BUDGET" | tail -n1 | cut -d= -f2 | tr -d '\r')
stub_min_decrease=$(grep -E '^STUB_MIN_DECREASE_PER_PR=' "$BUDGET" | tail -n1 | cut -d= -f2 | tr -d '\r')
stub_max=${stub_max:-999}
stub_min_decrease=${stub_min_decrease:-0}

# Stub count on base (main)
base_content=$(git show "${BASE_REF}:${REGISTRY}" 2>/dev/null || true)
base_count=0
[ -n "$base_content" ] && base_count=$(echo "$base_content" | grep -c 'STATUS=stub' || true)

# Stub count on HEAD
head_count=0
[ -f "$REGISTRY" ] && head_count=$(grep -c 'STATUS=stub' "$REGISTRY" || true)

SSOT_REGISTRY_STUB_COUNT_BASE=$base_count
SSOT_REGISTRY_STUB_COUNT_HEAD=$head_count

# 1) HEAD must not exceed STUB_MAX
if [ "$head_count" -gt "$stub_max" ]; then
  echo "ERROR_CODE=STUB_BUDGET_EXCEEDED"
  echo "STUB_COUNT=${head_count}"
  exit 1
fi

# 2) When base has stubs: must not increase, and decrease >= MIN_DECREASE
if [ "$base_count" -gt 0 ]; then
  if [ "$head_count" -gt "$base_count" ]; then
    echo "ERROR_CODE=STUB_COUNT_INCREASED"
    echo "BASE=${base_count}"
    echo "HEAD=${head_count}"
    exit 1
  fi
  decrease=$((base_count - head_count))
  if [ "$decrease" -lt "$stub_min_decrease" ]; then
    echo "ERROR_CODE=STUB_BURNDOWN_INSUFFICIENT"
    echo "BASE=${base_count}"
    echo "HEAD=${head_count}"
    exit 1
  fi
fi

SSOT_REGISTRY_STUB_BURNDOWN_OK=1
exit 0
