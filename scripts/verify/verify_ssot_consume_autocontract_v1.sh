#!/usr/bin/env bash
set -euo pipefail

SSOT_CONSUME_AUTOCONTRACT_OK=0
finish() { echo "SSOT_CONSUME_AUTOCONTRACT_OK=${SSOT_CONSUME_AUTOCONTRACT_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

BASE_REF="${SSOT_CONSUME_BASE_REF:-origin/main}"
git rev-parse --verify "$BASE_REF" >/dev/null 2>&1 || { echo "ERROR_CODE=BASE_REF_UNAVAILABLE"; exit 1; }

# Committed: base...HEAD
ssot_committed=$(git diff --name-only "$BASE_REF"...HEAD -- "docs/ops/contracts/" 2>/dev/null | grep -E '\.(txt|md|json)$' || true)
consumer_committed=$(git diff --name-only "$BASE_REF"...HEAD -- scripts/verify/ scripts/ops/ .github/workflows/ tools/ 2>/dev/null | grep -c . || true)

# Uncommitted: HEAD vs working tree
ssot_uncommitted=$(git diff --name-only HEAD -- "docs/ops/contracts/" 2>/dev/null | grep -E '\.(txt|md|json)$' || true)
consumer_uncommitted=$(git diff --name-only HEAD -- scripts/verify/ scripts/ops/ .github/workflows/ tools/ 2>/dev/null | grep -c . || true)

# If SSOT changed in committed diff, at least one consumer must change in that same diff
if [ -n "$ssot_committed" ] && [ "${consumer_committed:-0}" -lt 1 ]; then
  first_ssot=$(echo "$ssot_committed" | head -n1)
  echo "ERROR_CODE=SSOT_CHANGED_WITHOUT_CONSUMER_CHANGE"
  echo "HIT_SSOT=${first_ssot}"
  exit 1
fi

# If SSOT changed in uncommitted diff, at least one consumer must change in that same diff
if [ -n "$ssot_uncommitted" ] && [ "${consumer_uncommitted:-0}" -lt 1 ]; then
  first_ssot=$(echo "$ssot_uncommitted" | head -n1)
  echo "ERROR_CODE=SSOT_CHANGED_WITHOUT_CONSUMER_CHANGE"
  echo "HIT_SSOT=${first_ssot}"
  exit 1
fi

SSOT_CONSUME_AUTOCONTRACT_OK=1
exit 0
