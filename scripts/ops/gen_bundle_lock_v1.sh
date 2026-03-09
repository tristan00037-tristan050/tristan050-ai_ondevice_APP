#!/usr/bin/env bash
set -euo pipefail

# gen_bundle_lock_v1.sh
# BUNDLE_LOCK_V1 report generator (P22-P2-01)
# Produces docs/ops/reports/bundle_lock_v1_latest.json
# - Required fields: bundle_id, bundle_lock_version, manifest_digest_sha256,
#   sbom_digest_sha256, provenance_digest_sha256, proof_digest_sha256,
#   tuf_root_digest_sha256
# - Optional fields (omitted if source files not present):
#   model_pack_digest_sha256, retrieval_pack_digest_sha256
# - Self-referencing: lock_digest_sha256 computed over the final JSON (file sha256)
# - Canonical JSON: keys alphabetically sorted
# - generated_at_utc and git_sha included

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/BUNDLE_LOCK_V1.txt"
[[ -f "$SSOT" ]] || { echo "BLOCK: missing $SSOT"; exit 1; }
grep -q '^BUNDLE_LOCK_V1_TOKEN=1' "$SSOT" || { echo "BLOCK: missing token in $SSOT"; exit 1; }

OUTPUT_PATH="$(grep '^OUTPUT_PATH=' "$SSOT" | head -1 | sed 's/^OUTPUT_PATH=//' | tr -d '\r')"
[[ -n "$OUTPUT_PATH" ]] || { echo "BLOCK: OUTPUT_PATH not found in $SSOT"; exit 1; }
mkdir -p "$(dirname "$OUTPUT_PATH")"

GIT_SHA="$(git rev-parse HEAD)"
GENERATED_AT_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

sha256_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then echo "MISSING"; return; fi
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$f" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$f" | awk '{print $1}'
  else
    echo "UNAVAILABLE"
  fi
}

# Required source files
MANIFEST_FILE="${BUNDLE_LOCK_MANIFEST_FILE:-dist/algo_core_manifest.json}"
SBOM_FILE="${BUNDLE_LOCK_SBOM_FILE:-docs/ops/reports/artifact_bundle_latest.json}"
PROVENANCE_FILE="${BUNDLE_LOCK_PROVENANCE_FILE:-docs/ops/reports/artifact_bundle_latest.json}"
PROOF_FILE="${BUNDLE_LOCK_PROOF_FILE:-docs/ops/PROOFS/artifact_chain_proof_v2_latest.json}"
TUF_ROOT_FILE="${BUNDLE_LOCK_TUF_ROOT_FILE:-tuf/repository/1.root.json}"

# Optional source files
MODEL_PACK_FILE="${BUNDLE_LOCK_MODEL_PACK_FILE:-}"
RETRIEVAL_PACK_FILE="${BUNDLE_LOCK_RETRIEVAL_PACK_FILE:-}"

# Fail-closed: required artifacts must exist
for _req in "$MANIFEST_FILE" "$SBOM_FILE" "$PROVENANCE_FILE" "$PROOF_FILE" "$TUF_ROOT_FILE"; do
  [[ -f "$_req" ]] || { echo "ERROR_CODE=BUNDLE_LOCK_REQUIRED_ARTIFACT_MISSING"; echo "MISSING_FILE=$_req"; exit 1; }
done

MANIFEST_DIGEST="$(sha256_file "$MANIFEST_FILE")"
SBOM_DIGEST="$(sha256_file "$SBOM_FILE")"
PROVENANCE_DIGEST="$(sha256_file "$PROVENANCE_FILE")"
PROOF_DIGEST="$(sha256_file "$PROOF_FILE")"
TUF_ROOT_DIGEST="$(sha256_file "$TUF_ROOT_FILE")"

BUNDLE_ID="${BUNDLE_LOCK_BUNDLE_ID:-artifact_bundle_v1}"
BUNDLE_LOCK_VERSION="${BUNDLE_LOCK_VERSION:-1}"

# Build JSON using python3 for canonical (sorted-key) output
PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "BLOCK: python3/python not found"; exit 1; }

# Build payload dict in python, then produce canonical sorted JSON, then compute sha256
"$PYTHON_BIN" - <<PYEOF "$OUTPUT_PATH" "$GIT_SHA" "$GENERATED_AT_UTC" \
  "$BUNDLE_ID" "$BUNDLE_LOCK_VERSION" \
  "$MANIFEST_DIGEST" "$SBOM_DIGEST" "$PROVENANCE_DIGEST" "$PROOF_DIGEST" "$TUF_ROOT_DIGEST" \
  "${MODEL_PACK_FILE}" "${RETRIEVAL_PACK_FILE}"
import json, hashlib, sys, os

out_path, git_sha, generated_at, bundle_id, bundle_lock_version, \
  manifest_d, sbom_d, provenance_d, proof_d, tuf_root_d, \
  model_pack_file, retrieval_pack_file = sys.argv[1:]

def sha256_file(path):
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

payload = {
    "bundle_id": bundle_id,
    "bundle_lock_version": int(bundle_lock_version),
    "generated_at_utc": generated_at,
    "git_sha": git_sha,
    "manifest_digest_sha256": manifest_d,
    "proof_digest_sha256": proof_d,
    "provenance_digest_sha256": provenance_d,
    "sbom_digest_sha256": sbom_d,
    "tuf_root_digest_sha256": tuf_root_d,
}

# Optional fields (only include if files present)
model_digest = sha256_file(model_pack_file) if model_pack_file else None
retrieval_digest = sha256_file(retrieval_pack_file) if retrieval_pack_file else None
if model_digest:
    payload["model_pack_digest_sha256"] = model_digest
if retrieval_digest:
    payload["retrieval_pack_digest_sha256"] = retrieval_digest

# Self-referencing: hash JSON WITHOUT lock_digest_sha256 key, then insert
canonical_no_digest = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2)
lock_digest = hashlib.sha256(canonical_no_digest.encode('utf-8')).hexdigest()
payload["lock_digest_sha256"] = lock_digest

# Final canonical JSON with real digest
final_json = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2)

with open(out_path, 'w', encoding='utf-8') as f:
    f.write(final_json + '\n')

print(f"OK: wrote {out_path}")
print(f"OK: lock_digest_sha256={lock_digest}")
PYEOF
