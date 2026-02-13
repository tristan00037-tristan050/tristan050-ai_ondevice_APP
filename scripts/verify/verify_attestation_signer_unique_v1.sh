#!/usr/bin/env bash
set -euo pipefail

SLSA_SIGNER_WORKFLOW_UNIQUE_V1_OK=0
trap 'echo "SLSA_SIGNER_WORKFLOW_UNIQUE_V1_OK=$SLSA_SIGNER_WORKFLOW_UNIQUE_V1_OK"' EXIT

f=".github/workflows/product-verify-supplychain.yml"
[ -f "$f" ] || { echo "BLOCK: missing $f"; exit 1; }

# jobs: 이전(워크플로 헤더) 구간에 write 권한이 있으면 BLOCK
awk '
  BEGIN{in_hdr=1}
  /^jobs:/ {in_hdr=0}
  { if(in_hdr==1) print $0 }
' "$f" | grep -Eq '(id-token[[:space:]]*:[[:space:]]*["'"'"']?write["'"'"']?|attestations[[:space:]]*:[[:space:]]*["'"'"']?write["'"'"']?|artifact-metadata[[:space:]]*:[[:space:]]*["'"'"']?write["'"'"']?)' \
  && { echo "BLOCK: workflow-level write permissions found in supplychain header"; exit 1; } || true

SLSA_SIGNER_WORKFLOW_UNIQUE_V1_OK=1
exit 0

