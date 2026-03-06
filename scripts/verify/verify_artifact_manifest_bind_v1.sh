#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_MANIFEST_BIND_POLICY_V1_OK=0
ARTIFACT_MANIFEST_PRESENT_OK=0
ARTIFACT_MANIFEST_DIGEST_MATCH_OK=0
trap 'echo "ARTIFACT_MANIFEST_BIND_POLICY_V1_OK=${ARTIFACT_MANIFEST_BIND_POLICY_V1_OK}"; echo "ARTIFACT_MANIFEST_PRESENT_OK=${ARTIFACT_MANIFEST_PRESENT_OK}"; echo "ARTIFACT_MANIFEST_DIGEST_MATCH_OK=${ARTIFACT_MANIFEST_DIGEST_MATCH_OK}"' EXIT

ENFORCE="${ARTIFACT_MANIFEST_BIND_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "ARTIFACT_MANIFEST_BIND_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/ARTIFACT_MANIFEST_BIND_V1.md"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=ARTIFACT_MANIFEST_BIND_SSOT_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi
grep -q 'ARTIFACT_MANIFEST_BIND_V1_TOKEN=1' "$SSOT" || {
  echo "ERROR_CODE=ARTIFACT_MANIFEST_BIND_SSOT_INVALID"
  echo "HIT_PATH=$SSOT"
  exit 1
}

# Paths from SSOT or default
get_ssot_var() {
  local key="$1"
  local default="$2"
  if grep -qE "^${key}=" "$SSOT" 2>/dev/null; then
    grep -E "^${key}=" "$SSOT" | head -n1 | sed "s/^${key}=//" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
  else
    echo "$default"
  fi
}
ARTIFACT_MANIFEST_PATH="$(get_ssot_var "ARTIFACT_MANIFEST_PATH" "out/ops/artifacts/manifest.json")"
ARTIFACT_DIGEST_PATH="$(get_ssot_var "ARTIFACT_DIGEST_PATH" "out/ops/artifacts/digest.json")"

# 1) Manifest file exists
if [ ! -f "$ARTIFACT_MANIFEST_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_MANIFEST_MISSING"
  echo "HIT_PATH=$ARTIFACT_MANIFEST_PATH"
  exit 1
fi
ARTIFACT_MANIFEST_PRESENT_OK=1

# 2) Digest file exists and has sha (or digest) field
if [ ! -f "$ARTIFACT_DIGEST_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_DIGEST_MISSING"
  echo "HIT_PATH=$ARTIFACT_DIGEST_PATH"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR_CODE=ARTIFACT_MANIFEST_BIND_NODE_UNAVAILABLE"
  exit 1
fi

# 3) Both valid JSON; digest has sha or digest field; manifest and digest value match
set +e
node -e "
const fs = require('fs');
const manifestPath = process.argv[1];
const digestPath = process.argv[2];
let manifest, digest;
try {
  manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
} catch (e) { process.exit(10); }
if (!manifest || typeof manifest !== 'object') process.exit(10);
try {
  digest = JSON.parse(fs.readFileSync(digestPath, 'utf8'));
} catch (e) { process.exit(11); }
if (!digest || typeof digest !== 'object') process.exit(11);
const digestSha = digest.sha || digest.digest;
if (typeof digestSha !== 'string' || !digestSha) process.exit(11);
const manifestSha = manifest.sha || manifest.digest;
if (typeof manifestSha !== 'string' || !manifestSha) process.exit(12);
if (manifestSha !== digestSha) process.exit(12);
process.exit(0);
" "$ARTIFACT_MANIFEST_PATH" "$ARTIFACT_DIGEST_PATH" 2>/dev/null
rc=$?
set -e
if [ "$rc" -eq 10 ]; then
  echo "ERROR_CODE=ARTIFACT_MANIFEST_INVALID"
  echo "HIT_PATH=$ARTIFACT_MANIFEST_PATH"
  exit 1
fi
if [ "$rc" -eq 11 ]; then
  echo "ERROR_CODE=ARTIFACT_DIGEST_MISSING"
  echo "HIT_PATH=$ARTIFACT_DIGEST_PATH"
  exit 1
fi
if [ "$rc" -eq 12 ]; then
  echo "ERROR_CODE=ARTIFACT_MANIFEST_DIGEST_MISMATCH"
  echo "HIT_PATH=$ARTIFACT_MANIFEST_PATH"
  exit 1
fi
if [ "$rc" -ne 0 ]; then
  echo "ERROR_CODE=ARTIFACT_MANIFEST_BIND_UNEXPECTED_RC"
  echo "HIT_RC=$rc"
  exit 1
fi

ARTIFACT_MANIFEST_DIGEST_MATCH_OK=1
ARTIFACT_MANIFEST_BIND_POLICY_V1_OK=1
exit 0
