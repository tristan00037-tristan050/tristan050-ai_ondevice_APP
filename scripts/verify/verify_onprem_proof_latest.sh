#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

LATEST="docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md"
INDEX="docs/ops/PROOFS/INDEX.md"
PATTERNS="docs/ops/contracts/PROOF_SENSITIVE_PATTERNS_V1.txt"

ONPREM_PROOF_LATEST_PRESENT_OK=0
ONPREM_PROOF_ARCHIVE_LINKED_OK=0
ONPREM_PROOF_SENSITIVE_SCAN_OK=0

[[ -s "$LATEST" ]] || { echo "BLOCK: LATEST missing/empty: $LATEST"; exit 1; }
ONPREM_PROOF_LATEST_PRESENT_OK=1

if [[ -s "$INDEX" ]] \
  && grep -qF "ONPREM_REAL_WORLD_PROOF_LATEST.md" "$INDEX" \
  && grep -qF "docs/ops/PROOFS/archive/" "$INDEX"
then
  ONPREM_PROOF_ARCHIVE_LINKED_OK=1
else
  echo "BLOCK: INDEX missing or not linked: $INDEX"
  exit 1
fi

[[ -s "$PATTERNS" ]] || { echo "BLOCK: patterns missing/empty: $PATTERNS"; exit 1; }

if grep -nFf "$PATTERNS" "$LATEST" >/dev/null; then
  echo "BLOCK: sensitive pattern detected in LATEST"
  grep -nFf "$PATTERNS" "$LATEST" | sed 's/:.*$//' | head -n 20 || true
  exit 1
fi

awk 'length($0) > 500 { print "BLOCK: long line at " NR " len=" length($0); exit 1 }' "$LATEST"

ONPREM_PROOF_SENSITIVE_SCAN_OK=1

echo "ONPREM_PROOF_LATEST_PRESENT_OK=$ONPREM_PROOF_LATEST_PRESENT_OK"
echo "ONPREM_PROOF_ARCHIVE_LINKED_OK=$ONPREM_PROOF_ARCHIVE_LINKED_OK"
echo "ONPREM_PROOF_SENSITIVE_SCAN_OK=$ONPREM_PROOF_SENSITIVE_SCAN_OK"
