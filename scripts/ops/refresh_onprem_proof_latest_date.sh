#!/usr/bin/env bash
# Proof 내용은 유지하고, freshness 가드용 날짜(ts_utc)만 오늘(UTC)로 갱신.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
LATEST="docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md"
[[ -s "$LATEST" ]] || { echo "BLOCK: missing/empty $LATEST"; exit 1; }
TODAY_UTC="$(date -u +%Y-%m-%dT00:00:00Z)"
TMP="$(mktemp)"
sed -E "s/^ts_utc=.*/ts_utc=${TODAY_UTC}/" "$LATEST" > "$TMP" && mv "$TMP" "$LATEST"
echo "OK: ts_utc set to $TODAY_UTC in $LATEST"
