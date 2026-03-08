#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_CHAIN_PROOF_V2_OK=0
trap 'echo "ARTIFACT_CHAIN_PROOF_V2_OK=${ARTIFACT_CHAIN_PROOF_V2_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PROOF="docs/ops/proofs/artifact_chain_proof_v2_latest.json"
[[ -f "$PROOF" ]] || { echo "ERROR_CODE=ARTIFACT_CHAIN_PROOF_MISSING"; echo "HIT_PATH=$PROOF"; exit 1; }

node - "$PROOF" <<'NODESCRIPT'
const fs = require('fs');
const proofPath = process.argv[2];
const raw = fs.readFileSync(proofPath, 'utf8');
const obj = JSON.parse(raw);

const requiredTop = [
  'proof_version','bundle_id','verified_at_utc','git_sha','environment_id',
  'verifier_results','manifest_digest_sha256','sbom_digest_sha256',
  'provenance_digest_sha256','result_fingerprint_sha256'
];

for (const k of requiredTop) {
  if (!(k in obj)) {
    console.log('ERROR_CODE=ARTIFACT_CHAIN_PROOF_KEY_MISSING');
    console.log('HIT_KEY=' + k);
    process.exit(1);
  }
}

if (obj.proof_version !== 2) {
  console.log('ERROR_CODE=ARTIFACT_CHAIN_PROOF_VERSION_INVALID');
  process.exit(1);
}

const vr = obj.verifier_results || {};
for (const k of [
  'tuf_min_signing_chain',
  'sbom_from_artifacts',
  'manifest_bind',
  'bundle_integrity',
  'provenance_link',
  'verifier_chain'
]) {
  if (vr[k] !== 'ok') {
    console.log('ERROR_CODE=ARTIFACT_CHAIN_PROOF_RESULT_INVALID');
    console.log('HIT_KEY=' + k);
    process.exit(1);
  }
}

const forbidden = new Set(['raw','origin','content','body','full_output','stdout','stderr']);
function walk(v, depth) {
  if (depth > 5) {
    console.log('ERROR_CODE=ARTIFACT_CHAIN_PROOF_DEPTH_EXCEEDED');
    process.exit(1);
  }
  if (typeof v === 'string' && v.length > 500) {
    console.log('ERROR_CODE=ARTIFACT_CHAIN_PROOF_STRING_TOO_LONG');
    process.exit(1);
  }
  if (Array.isArray(v)) {
    for (const x of v) walk(x, depth + 1);
    return;
  }
  if (v && typeof v === 'object') {
    for (const [k, val] of Object.entries(v)) {
      if (forbidden.has(k)) {
        console.log('ERROR_CODE=ARTIFACT_CHAIN_PROOF_META_ONLY_VIOLATION');
        console.log('HIT_KEY=' + k);
        process.exit(1);
      }
      walk(val, depth + 1);
    }
  }
}
walk(obj, 0);
NODESCRIPT

ARTIFACT_CHAIN_PROOF_V2_OK=1
exit 0
