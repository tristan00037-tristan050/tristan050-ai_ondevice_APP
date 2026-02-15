#!/usr/bin/env bash
set -euo pipefail

HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK=0
HIGH_RISK_TAINT_PROPAGATION_OK=0
HIGH_RISK_APPROVAL_FORMAT_OK=0

cleanup() {
  echo "HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK=${HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK}"
  echo "HIGH_RISK_TAINT_PROPAGATION_OK=${HIGH_RISK_TAINT_PROPAGATION_OK}"
  echo "HIGH_RISK_APPROVAL_FORMAT_OK=${HIGH_RISK_APPROVAL_FORMAT_OK}"

  if [[ "$HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK" == "1" ]] && \
     [[ "$HIGH_RISK_TAINT_PROPAGATION_OK" == "1" ]] && \
     [[ "$HIGH_RISK_APPROVAL_FORMAT_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

OUT="$(node scripts/agent/high_risk_gate_selftest_v1.cjs 2>&1)" || { echo "BLOCK: high risk gate selftest failed"; echo "$OUT"; exit 1; }

echo "$OUT" | grep -nE '^HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK=1$' >/dev/null || exit 1
HIGH_RISK_BLOCK_WITHOUT_APPROVAL_OK=1

echo "$OUT" | grep -nE '^HIGH_RISK_TAINT_PROPAGATION_OK=1$' >/dev/null || exit 1
HIGH_RISK_TAINT_PROPAGATION_OK=1

echo "$OUT" | grep -nE '^HIGH_RISK_APPROVAL_FORMAT_OK=1$' >/dev/null || exit 1
HIGH_RISK_APPROVAL_FORMAT_OK=1

exit 0

