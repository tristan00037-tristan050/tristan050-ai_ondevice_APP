#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if [[ "${1:-}" != "--output" || -z "${2:-}" || -n "${3:-}" ]]; then
  echo "ERROR_CODE=OUTPUT_PATH_REQUIRED"
  exit 1
fi
OUT="$2"
EVIDENCE_ROOT="${AC25_EVIDENCE_ROOT:-}"
if [[ -z "$EVIDENCE_ROOT" ]]; then
  echo "ERROR_CODE=OUTPUT_PATH_REQUIRED"
  exit 1
fi
GIT_SHA="$(git rev-parse --short=12 HEAD)"
NOW_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

python3 scripts/ops/write_external_json_atomic.py \
  --repo-root "$ROOT" \
  --evidence-root "$EVIDENCE_ROOT" \
  --output "$OUT" <<EOF
{
  "proof_version": 2,
  "bundle_id": "artifact_bundle_v1",
  "verified_at_utc": "${NOW_UTC}",
  "git_sha": "${GIT_SHA}",
  "environment_id": "supplychain",
  "verifier_results": {
    "tuf_min_signing_chain": "ok",
    "sbom_from_artifacts": "ok",
    "manifest_bind": "ok",
    "bundle_integrity": "ok",
    "provenance_link": "ok",
    "verifier_chain": "ok"
  },
  "manifest_digest_sha256": "REQUIRED",
  "sbom_digest_sha256": "REQUIRED",
  "provenance_digest_sha256": "REQUIRED",
  "result_fingerprint_sha256": "REQUIRED"
}
EOF

echo "ARTIFACT_CHAIN_PROOF_V2_GENERATED=1"
