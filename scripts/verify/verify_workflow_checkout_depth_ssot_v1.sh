#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_CHECKOUT_DEPTH_SSOT_OK=0
finish() { echo "WORKFLOW_CHECKOUT_DEPTH_SSOT_OK=${WORKFLOW_CHECKOUT_DEPTH_SSOT_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/WORKFLOW_CHECKOUT_DEPTH_SSOT_V1.txt"
test -f "$SSOT" || { echo "ERROR_CODE=SSOT_MISSING"; exit 1; }
grep -q '^WORKFLOW_CHECKOUT_DEPTH_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=SSOT_TOKEN_MISSING"; exit 1; }

req_count="$(grep -c '^REQUIRE_FETCH_DEPTH_0=' "$SSOT" || true)"
if [ "$req_count" -le 0 ]; then
  echo "ERROR_CODE=SSOT_WORKFLOW_LIST_EMPTY"
  exit 1
fi

while IFS= read -r line || [ -n "$line" ]; do
  [[ "$line" =~ ^REQUIRE_FETCH_DEPTH_0=(.+)$ ]] || continue
  wf="${BASH_REMATCH[1]}"
  wf="${wf%"${wf##*[![:space:]]}"}"
  [ -f "$wf" ] || { echo "ERROR_CODE=CHECKOUT_FETCH_DEPTH_0_MISSING"; echo "HIT_WORKFLOW=${wf}"; exit 1; }

  checkout_count="$(grep -c "actions/checkout@v4" "$wf" || true)"
  if [ "$checkout_count" -le 0 ]; then
    echo "ERROR_CODE=CHECKOUT_FETCH_DEPTH_0_MISSING"
    echo "HIT_WORKFLOW=${wf}"
    exit 1
  fi

  bad=0
  while IFS= read -r ln; do
    if ! sed -n "${ln},$((ln+6))p" "$wf" | grep -q "fetch-depth:[[:space:]]*0"; then
      bad=1
      break
    fi
  done < <(grep -n "actions/checkout@v4" "$wf" | cut -d: -f1)

  if [ "$bad" -ne 0 ]; then
    echo "ERROR_CODE=CHECKOUT_FETCH_DEPTH_0_MISSING"
    echo "HIT_WORKFLOW=${wf}"
    exit 1
  fi
done < <(grep '^REQUIRE_FETCH_DEPTH_0=' "$SSOT")

WORKFLOW_CHECKOUT_DEPTH_SSOT_OK=1
exit 0
