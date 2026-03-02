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

while IFS= read -r line || [ -n "$line" ]; do
  [[ "$line" =~ ^REQUIRE_FETCH_DEPTH_0=(.+)$ ]] || continue
  wf="${BASH_REMATCH[1]}"
  wf="${wf%"${wf##*[![:space:]]}"}"
  [ -f "$wf" ] || { echo "ERROR_CODE=CHECKOUT_FETCH_DEPTH_0_MISSING"; echo "HIT_WORKFLOW=${wf}"; exit 1; }
  grep -q "actions/checkout@v4" "$wf" || { echo "ERROR_CODE=CHECKOUT_FETCH_DEPTH_0_MISSING"; echo "HIT_WORKFLOW=${wf}"; exit 1; }
  grep -A 6 "actions/checkout@v4" "$wf" | grep -q "fetch-depth: 0" || { echo "ERROR_CODE=CHECKOUT_FETCH_DEPTH_0_MISSING"; echo "HIT_WORKFLOW=${wf}"; exit 1; }
done < <(grep '^REQUIRE_FETCH_DEPTH_0=' "$SSOT")

WORKFLOW_CHECKOUT_DEPTH_SSOT_OK=1
exit 0
