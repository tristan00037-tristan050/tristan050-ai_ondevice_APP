#!/usr/bin/env bash
set -euo pipefail

SUPPLYCHAIN_PERMISSIONS_SCOPED_V1_OK=0
trap 'echo "SUPPLYCHAIN_PERMISSIONS_SCOPED_V1_OK=$SUPPLYCHAIN_PERMISSIONS_SCOPED_V1_OK"' EXIT

ALLOW=".github/workflows/product-verify-supplychain.yml"
[ -f "$ALLOW" ] || { echo "BLOCK: missing $ALLOW"; exit 1; }

FORBIDDEN_RE='(id-token[[:space:]]*:[[:space:]]*["'"'"']?write["'"'"']?|attestations[[:space:]]*:[[:space:]]*["'"'"']?write["'"'"']?|artifact-metadata[[:space:]]*:[[:space:]]*["'"'"']?write["'"'"']?|attest-build-provenance)'

bad=0
for f in .github/workflows/*.yml; do
  [ "$f" = "$ALLOW" ] && continue
  if grep -Eq "$FORBIDDEN_RE" "$f"; then
    echo "BLOCK: forbidden attestation perms/step outside supplychain: $f"
    bad=1
  fi
done
[ "$bad" = "0" ] || exit 1

SUPPLYCHAIN_PERMISSIONS_SCOPED_V1_OK=1
exit 0

