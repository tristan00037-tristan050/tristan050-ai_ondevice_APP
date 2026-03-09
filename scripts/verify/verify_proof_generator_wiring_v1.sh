#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_CHAIN_PROOF_GENERATOR_V1_OK=0
ARTIFACT_CHAIN_PROOF_ENFORCE_WIRING_OK=0
trap 'echo "ARTIFACT_CHAIN_PROOF_GENERATOR_V1_OK=${ARTIFACT_CHAIN_PROOF_GENERATOR_V1_OK}"; echo "ARTIFACT_CHAIN_PROOF_ENFORCE_WIRING_OK=${ARTIFACT_CHAIN_PROOF_ENFORCE_WIRING_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

verify_step_order() {
  local wf="$1"
  local gen_script="gen_artifact_chain_proof_v2.sh"
  local verify_script="verify_repo_contracts.sh"

  local gen_line verify_line
  gen_line="$(grep -n "$gen_script" "$wf" 2>/dev/null | head -1 | cut -d: -f1 || true)"
  verify_line="$(grep -n "$verify_script" "$wf" 2>/dev/null | head -1 | cut -d: -f1 || true)"

  if [[ -z "$gen_line" ]]; then
    echo "ERROR_CODE=PROOF_GENERATOR_STEP_MISSING"
    echo "WORKFLOW=$wf"
    exit 1
  fi
  if [[ -z "$verify_line" ]]; then
    echo "ERROR_CODE=PROOF_VERIFY_STEP_MISSING"
    echo "WORKFLOW=$wf"
    exit 1
  fi
  if [[ "$gen_line" -ge "$verify_line" ]]; then
    echo "ERROR_CODE=PROOF_GENERATOR_MUST_RUN_BEFORE_VERIFY"
    echo "WORKFLOW=$wf"
    echo "GEN_LINE=$gen_line"
    echo "VERIFY_LINE=$verify_line"
    exit 1
  fi
}

WFS=(
  ".github/workflows/product-verify-repo-guards.yml"
  ".github/workflows/release.yml"
)

for wf in "${WFS[@]}"; do
  [[ -f "$ROOT/$wf" ]] || { echo "ERROR_CODE=PROOF_WIRING_WORKFLOW_MISSING"; echo "WORKFLOW=$wf"; exit 1; }
  verify_step_order "$ROOT/$wf"
  grep -q 'ARTIFACT_CHAIN_PROOF_V2_ENFORCE.*"1"' "$ROOT/$wf" || {
    echo "ERROR_CODE=PROOF_ENFORCE_ENV_MISSING"
    echo "WORKFLOW=$wf"
    exit 1
  }
done

ARTIFACT_CHAIN_PROOF_GENERATOR_V1_OK=1
ARTIFACT_CHAIN_PROOF_ENFORCE_WIRING_OK=1
exit 0
