#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_CHECKOUT_DEPTH_AUTODISCOVER_OK=0
finish() { echo "WORKFLOW_CHECKOUT_DEPTH_AUTODISCOVER_OK=${WORKFLOW_CHECKOUT_DEPTH_AUTODISCOVER_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Full-history trigger: workflow runs one of these scripts
FULL_HISTORY_MARKER_1="verify_base_ref_available_v1.sh"
FULL_HISTORY_MARKER_2="verify_repo_contracts.sh"
# Look-ahead lines for fetch-depth: 0 after actions/checkout@v4
DEPTH_LINES=10
SSOT="docs/ops/contracts/WORKFLOW_CHECKOUT_DEPTH_SSOT_V1.txt"

need_full() {
  local wf="$1"
  grep -q "$FULL_HISTORY_MARKER_1" "$wf" 2>/dev/null && return 0
  grep -q "$FULL_HISTORY_MARKER_2" "$wf" 2>/dev/null && return 0
  return 1
}

check_every_checkout_has_depth_zero() {
  local wf="$1"
  local ln
  while IFS= read -r ln; do
    if ! sed -n "${ln},$((ln + DEPTH_LINES))p" "$wf" | grep -q "fetch-depth:[[:space:]]*0"; then
      return 1
    fi
  done < <(grep -n "actions/checkout@v4" "$wf" | cut -d: -f1)
  return 0
}

# 1) Auto-discover: every .github/workflows/*.yml that needs full history must have fetch-depth: 0 on every checkout
for wf in .github/workflows/*.yml; do
  [ -f "$wf" ] || continue
  if ! need_full "$wf"; then
    continue
  fi
  if ! check_every_checkout_has_depth_zero "$wf"; then
    echo "ERROR_CODE=CHECKOUT_FETCH_DEPTH_0_MISSING"
    echo "HIT_WORKFLOW=${wf}"
    exit 1
  fi
done

# 2) SSOT drift: every auto-discovered full-history workflow must be listed in SSOT
if [ -f "$SSOT" ]; then
  for wf in .github/workflows/*.yml; do
    [ -f "$wf" ] || continue
    if ! need_full "$wf"; then
      continue
    fi
    if ! grep -q "^REQUIRE_FETCH_DEPTH_0=${wf}\$" "$SSOT" 2>/dev/null; then
      echo "ERROR_CODE=SSOT_MISSING_REQUIRED_WORKFLOW"
      echo "HIT_WORKFLOW=${wf}"
      exit 1
    fi
  done
fi

WORKFLOW_CHECKOUT_DEPTH_AUTODISCOVER_OK=1
exit 0
