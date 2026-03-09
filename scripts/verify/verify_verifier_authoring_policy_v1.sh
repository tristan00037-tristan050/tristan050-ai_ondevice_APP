#!/usr/bin/env bash
set -euo pipefail

VERIFIER_AUTHORING_POLICY_V1_OK=0
trap 'echo "VERIFIER_AUTHORING_POLICY_V1_OK=${VERIFIER_AUTHORING_POLICY_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/VERIFIER_AUTHORING_POLICY_V1.txt"
[[ -f "$SSOT" ]] || { echo "ERROR_CODE=VERIFIER_AUTHORING_SSOT_MISSING"; echo "HIT_PATH=$SSOT"; exit 1; }
grep -q '^VERIFIER_AUTHORING_POLICY_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=VERIFIER_AUTHORING_TOKEN_MISSING"; exit 1; }

TEMPLATE="scripts/ops/new_verifier_from_template_v1.sh"
[[ -f "$ROOT/$TEMPLATE" ]] || { echo "ERROR_CODE=VERIFIER_TEMPLATE_MISSING"; echo "HIT_PATH=$TEMPLATE"; exit 1; }

# Template must reference the policy SSOT token
grep -q 'VERIFIER_AUTHORING_POLICY_V1_TOKEN' "$ROOT/$TEMPLATE" || {
  echo "ERROR_CODE=VERIFIER_TEMPLATE_SSOT_BIND_MISSING"
  echo "HIT_PATH=$TEMPLATE"
  exit 1
}

# Template must be executable
[[ -x "$ROOT/$TEMPLATE" ]] || { echo "ERROR_CODE=VERIFIER_TEMPLATE_NOT_EXECUTABLE"; echo "HIT_PATH=$TEMPLATE"; exit 1; }

VERIFIER_AUTHORING_POLICY_V1_OK=1
exit 0
