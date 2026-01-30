#!/usr/bin/env bash
set -euo pipefail

NS="${1:-default}"
OUT="${2:-docs/ops/PROOFS/2026-01-30_runtime_egress_k8s_proof.md}"

command -v kubectl >/dev/null 2>&1 || { echo "BLOCK: kubectl not found"; exit 1; }

POD="$(kubectl -n "${NS}" get pod -l app=butler-runtime -o jsonpath="{.items[0].metadata.name}" 2>/dev/null || true)"
if [[ -z "${POD}" ]]; then
  echo "BLOCK: no butler-runtime pod found in ns=${NS} (label app=butler-runtime required)"
  exit 1
fi

{
  echo "# Runtime egress deny proof (Kubernetes)"
  echo
  echo "namespace: ${NS}"
  echo "pod: ${POD}"
  echo "expectation: outbound DNS/HTTP to public internet must FAIL"
  echo
  echo "## Attempt: DNS resolve (example.com) via node"
  echo '```'
  set +e
  kubectl -n "${NS}" exec "${POD}" -- node -e 'require("dns").lookup("example.com", (err) => { process.exit(err ? 1 : 0); });' 2>&1
  RC1=$?
  set -e
  echo "RC=${RC1}"
  echo '```'
  echo
  echo "## Attempt: HTTPS request (https://example.com) via node"
  echo '```'
  set +e
  kubectl -n "${NS}" exec "${POD}" -- node -e 'require("https").get("https://example.com", () => {}).on("error", () => { process.exit(1); }); setTimeout(() => process.exit(0), 2000);' 2>&1
  RC2=$?
  set -e
  echo "RC=${RC2}"
  echo '```'
  echo
  echo "## Verdict"
  if [[ "${RC1}" -ne 0 && "${RC2}" -ne 0 ]]; then
    echo "RUNTIME_EGRESS_ENV_DENY_OK=1"
    echo "RUNTIME_EGRESS_ENV_PROOF_OK=1"
  else
    echo "RUNTIME_EGRESS_ENV_DENY_OK=0"
    echo "RUNTIME_EGRESS_ENV_PROOF_OK=0"
    echo "BLOCK: outbound attempt unexpectedly succeeded"
    exit 1
  fi
} > "${OUT}"

echo "OK: wrote ${OUT}"
