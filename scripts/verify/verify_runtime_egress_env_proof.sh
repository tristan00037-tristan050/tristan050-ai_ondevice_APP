#!/usr/bin/env bash
set -euo pipefail

RUNTIME_EGRESS_ENV_TEMPLATE_OK=0
RUNTIME_EGRESS_ENV_PROOF_OK=0

cleanup(){
  echo "RUNTIME_EGRESS_ENV_TEMPLATE_OK=${RUNTIME_EGRESS_ENV_TEMPLATE_OK}"
  echo "RUNTIME_EGRESS_ENV_PROOF_OK=${RUNTIME_EGRESS_ENV_PROOF_OK}"
  if [[ "${RUNTIME_EGRESS_ENV_TEMPLATE_OK}" == "1" ]] && [[ "${RUNTIME_EGRESS_ENV_PROOF_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

# templates must exist
test -s ops/onprem/compose/docker-compose.butler.internal.yml
test -s ops/k8s/networkpolicy/butler-runtime-egress-deny.yaml
RUNTIME_EGRESS_ENV_TEMPLATE_OK=1

# proofs must exist and contain PASS markers (ops scripts create these)
PROOF1="docs/ops/PROOFS/2026-01-30_runtime_egress_compose_proof.md"
PROOF2="docs/ops/PROOFS/2026-01-30_runtime_egress_k8s_proof.md"

test -s "${PROOF1}"
test -s "${PROOF2}"

grep -nF "RUNTIME_EGRESS_ENV_PROOF_OK=1" "${PROOF1}" >/dev/null
grep -nF "RUNTIME_EGRESS_ENV_PROOF_OK=1" "${PROOF2}" >/dev/null

RUNTIME_EGRESS_ENV_PROOF_OK=1
exit 0
