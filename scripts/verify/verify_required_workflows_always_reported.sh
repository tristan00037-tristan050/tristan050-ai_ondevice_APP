#!/usr/bin/env bash
set -euo pipefail

SSOT="docs/ops/contracts/REQUIRED_WORKFLOWS_SSOT.json"
[ -f "$SSOT" ] || { echo "BLOCK: missing SSOT: $SSOT"; exit 1; }

command -v jq >/dev/null 2>&1 || { echo "BLOCK: jq not found"; exit 1; }

mapfile -t reqs < <(jq -r '.required_workflows[]' "$SSOT")
[ "${#reqs[@]}" -ge 1 ] || { echo "BLOCK: empty required_workflows"; exit 1; }

WF_DIR=".github/workflows"
[ -d "$WF_DIR" ] || { echo "BLOCK: missing workflows dir: $WF_DIR"; exit 1; }

fail=0

for name in "${reqs[@]}"; do
  # 1) workflow file that contains this exact name:
  #    name: product-verify-...
  file="$(rg -l --fixed-strings "name: ${name}" "$WF_DIR" 2>/dev/null | head -n 1 || true)"
  if [ -z "$file" ]; then
    echo "BLOCK: workflow name not found in .github/workflows: ${name}"
    fail=1
    continue
  fi

  # 2) must include pull_request trigger
  if ! rg -n "^[[:space:]]*pull_request:" "$file" >/dev/null 2>&1; then
    echo "BLOCK: missing pull_request trigger: ${name} file=${file}"
    fail=1
  fi

  # 3) must include merge_group trigger
  if ! rg -n "^[[:space:]]*merge_group:" "$file" >/dev/null 2>&1; then
    echo "BLOCK: missing merge_group trigger: ${name} file=${file}"
    fail=1
  fi

  # 4) basic bypass patterns (best-effort static)
  if rg -n "continue-on-error:[[:space:]]*true" "$file" >/dev/null 2>&1; then
    echo "BLOCK: continue-on-error true found: ${name} file=${file}"
    fail=1
  fi

  echo "OK: REQUIRED_WORKFLOW_ALWAYS_REPORTED: ${name} file=${file}"
done

if [ "$fail" -ne 0 ]; then
  echo "REQUIRED_WORKFLOWS_ALWAYS_REPORTED_OK=0"
  exit 1
fi

echo "REQUIRED_WORKFLOWS_ALWAYS_REPORTED_OK=1"
