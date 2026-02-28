#!/usr/bin/env bash
set -euo pipefail

WF=".github/workflows/release.yml"

test -f "$WF" || { echo "BLOCK: missing $WF"; exit 1; }

have_rg() { command -v rg >/dev/null 2>&1 && rg --version >/dev/null 2>&1; }

# 1) publish-and-deploy가 self-hosted인지(Phase1 SSOT)
if have_rg; then
  rg -n '^\s+publish-and-deploy:\s*$' "$WF" >/dev/null || { echo "BLOCK: publish-and-deploy job not found in $WF"; exit 1; }
else
  grep -nE '^\s+publish-and-deploy:\s*$' "$WF" >/dev/null || { echo "BLOCK: publish-and-deploy job not found in $WF"; exit 1; }
fi

# publish-and-deploy job block (with original file line numbers)
pub_block_linenos="$(awk '
  $0 ~ /^  publish-and-deploy:/ {job=1}
  job==1 {print NR ":" $0}
  job==1 && NR>1 && $0 ~ /^  [a-zA-Z0-9_-]+:/ && $0 !~ /^  publish-and-deploy:/ {exit}
' "$WF")"

# sanity: job block exists
[ -n "$pub_block_linenos" ] || { echo "BLOCK: failed to extract publish-and-deploy block"; exit 1; }

# runs-on must be self-hosted (Phase 1)
if have_rg; then
  echo "$pub_block_linenos" | rg -q 'runs-on:\s*\[\s*self-hosted' || { echo "BLOCK: publish-and-deploy must run on self-hosted (Phase 1)."; echo "hint: runs-on: [self-hosted, macOS, ARM64]"; exit 1; }
else
  echo "$pub_block_linenos" | grep -qE 'runs-on:\s*\[\s*self-hosted' || { echo "BLOCK: publish-and-deploy must run on self-hosted (Phase 1)."; echo "hint: runs-on: [self-hosted, macOS, ARM64]"; exit 1; }
fi

# Use local kubeconfig step must exist in the block
if have_rg; then
  echo "$pub_block_linenos" | rg -q 'Use local kubeconfig' || { echo "BLOCK: missing 'Use local kubeconfig' step in publish-and-deploy."; exit 1; }
else
  echo "$pub_block_linenos" | grep -qE 'Use local kubeconfig' || { echo "BLOCK: missing 'Use local kubeconfig' step in publish-and-deploy."; exit 1; }
fi

# 2) KUBECONFIG set must occur before kubectl cluster-info *within publish-and-deploy*
if have_rg; then
  kcfg_line="$(echo "$pub_block_linenos" | rg -n 'KUBECONFIG=\$CFG' | head -n1 | cut -d: -f1 || echo 0)"
  pre_line="$(echo "$pub_block_linenos" | rg -n 'kubectl cluster-info' | head -n1 | cut -d: -f1 || echo 0)"
else
  kcfg_line="$(echo "$pub_block_linenos" | grep -nE 'KUBECONFIG=\$CFG' | head -n1 | cut -d: -f1 || echo 0)"
  pre_line="$(echo "$pub_block_linenos" | grep -nE 'kubectl cluster-info' | head -n1 | cut -d: -f1 || echo 0)"
fi

if [ "${kcfg_line:-0}" -eq 0 ] || [ "${pre_line:-0}" -eq 0 ]; then
  echo "BLOCK: cannot locate KUBECONFIG set or kubectl cluster-info inside publish-and-deploy"
  echo "debug: kcfg_line=$kcfg_line pre_line=$pre_line"
  exit 1
fi

if [ "$kcfg_line" -gt "$pre_line" ]; then
  echo "BLOCK: publish-and-deploy runs kubectl cluster-info before setting KUBECONFIG. Fix step order."
  echo "debug: kcfg_line=$kcfg_line pre_line=$pre_line"
  exit 1
fi

echo "OK: release-bff Phase1 gate passed"
