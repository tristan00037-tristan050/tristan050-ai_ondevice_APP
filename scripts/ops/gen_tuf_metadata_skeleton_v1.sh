#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
SSOT="docs/ops/contracts/SECURE_UPDATE_TUF_PRINCIPLES_SSOT_V1.txt"
[ -f "$SSOT" ] || { echo "ERROR_CODE=SSOT_MISSING"; exit 1; }
grep -q '^SECURE_UPDATE_TUF_PRINCIPLES_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=SSOT_INVALID"; exit 1; }

TUF_META_ROOT="$(grep -E '^TUF_META_ROOT=' "$SSOT" | head -n1 | sed 's/^TUF_META_ROOT=//' | tr -d '\r')"
TUF_META_ROOT="${TUF_META_ROOT:-out/ops/tuf}"
mkdir -p "$TUF_META_ROOT"

# TUF-like minimal valid JSON (no real signatures yet)
expiry_root="$(date -u -v+365d '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d '+365 days' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo "2026-12-31T23:59:59Z")"
expiry_90="$(date -u -v+90d '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d '+90 days' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo "2026-05-31T23:59:59Z")"
expiry_30="$(date -u -v+30d '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d '+30 days' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo "2026-03-31T23:59:59Z")"
expiry_7="$(date -u -v+7d '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d '+7 days' '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo "2026-02-26T23:59:59Z")"

cat > "$TUF_META_ROOT/root.json" << ROOT
{
  "signed": {
    "_type": "root",
    "spec_version": "1.0",
    "version": 1,
    "expires": "$expiry_root",
    "keys": {},
    "roles": {
      "root": { "keyids": [], "threshold": 1 },
      "targets": { "keyids": [], "threshold": 1 },
      "snapshot": { "keyids": [], "threshold": 1 },
      "timestamp": { "keyids": [], "threshold": 1 }
    }
  },
  "signatures": []
}
ROOT

cat > "$TUF_META_ROOT/targets.json" << TARGETS
{
  "signed": {
    "_type": "targets",
    "spec_version": "1.0",
    "version": 1,
    "expires": "$expiry_90",
    "targets": {}
  },
  "signatures": []
}
TARGETS

cat > "$TUF_META_ROOT/snapshot.json" << SNAPSHOT
{
  "signed": {
    "_type": "snapshot",
    "spec_version": "1.0",
    "version": 1,
    "expires": "$expiry_30",
    "meta": {}
  },
  "signatures": []
}
SNAPSHOT

cat > "$TUF_META_ROOT/timestamp.json" << TIMESTAMP
{
  "signed": {
    "_type": "timestamp",
    "spec_version": "1.0",
    "version": 1,
    "expires": "$expiry_7",
    "meta": {}
  },
  "signatures": []
}
TIMESTAMP

echo "TUF_SKELETON_GENERATED=1"
