#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_BUNDLE_PROVENANCE_POLICY_V1_OK=0
ARTIFACT_PROVENANCE_PRESENT_OK=0
ARTIFACT_PROVENANCE_SUBJECT_MATCH_OK=0
trap 'echo "ARTIFACT_BUNDLE_PROVENANCE_POLICY_V1_OK=${ARTIFACT_BUNDLE_PROVENANCE_POLICY_V1_OK}"; echo "ARTIFACT_PROVENANCE_PRESENT_OK=${ARTIFACT_PROVENANCE_PRESENT_OK}"; echo "ARTIFACT_PROVENANCE_SUBJECT_MATCH_OK=${ARTIFACT_PROVENANCE_SUBJECT_MATCH_OK}"' EXIT

ENFORCE="${ARTIFACT_BUNDLE_PROVENANCE_LINK_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "ARTIFACT_BUNDLE_PROVENANCE_LINK_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/ARTIFACT_BUNDLE_PROVENANCE_LINK_V1.md"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_PROVENANCE_LINK_SSOT_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi
grep -q 'ARTIFACT_BUNDLE_PROVENANCE_LINK_V1_TOKEN=1' "$SSOT" || {
  echo "ERROR_CODE=ARTIFACT_BUNDLE_PROVENANCE_LINK_SSOT_INVALID"
  echo "HIT_PATH=$SSOT"
  exit 1
}

get_ssot_var() {
  local key="$1"
  local default="$2"
  if grep -qE "^${key}=" "$SSOT" 2>/dev/null; then
    grep -E "^${key}=" "$SSOT" | head -n1 | sed "s/^${key}=//" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
  else
    echo "$default"
  fi
}
ARTIFACT_PROVENANCE_PATH="$(get_ssot_var "ARTIFACT_PROVENANCE_PATH" "out/ops/provenance/attestation.json")"
ARTIFACT_DIGEST_PATH="$(get_ssot_var "ARTIFACT_DIGEST_PATH" "out/ops/artifacts/digest.json")"

# 1) Provenance file exists
if [ ! -f "$ARTIFACT_PROVENANCE_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_PROVENANCE_MISSING"
  echo "HIT_PATH=$ARTIFACT_PROVENANCE_PATH"
  exit 1
fi
ARTIFACT_PROVENANCE_PRESENT_OK=1

command -v node >/dev/null 2>&1 || {
  echo "ERROR_CODE=ARTIFACT_PROVENANCE_INVALID"
  exit 1
}

# 2) Parse provenance + subject digest + compare with digest file + link check
set +e
node -e "
const fs = require('fs');
const { EXIT } = require('./tools/verify-runtime/exit_codes_v1.cjs');
const provPath = process.argv[1];
const digestPath = process.argv[2];
let prov, digest;
try {
  prov = JSON.parse(fs.readFileSync(provPath, 'utf8'));
} catch (e) { process.exit(EXIT.JSON_INVALID); }
if (!prov || typeof prov !== 'object') process.exit(EXIT.JSON_INVALID);
try {
  digest = JSON.parse(fs.readFileSync(digestPath, 'utf8'));
} catch (e) { process.exit(EXIT.JSON_INVALID); }
if (!digest || typeof digest !== 'object') process.exit(EXIT.JSON_INVALID);

// Subject digest: in-toto subject[] or subject.digest
const subj = prov.subject;
if (!Array.isArray(subj) || subj.length === 0) process.exit(EXIT.SCHEMA_MISSING);
const first = subj[0];
if (!first || typeof first !== 'object') process.exit(EXIT.SCHEMA_MISSING);
const d = first.digest;
if (!d || typeof d !== 'object') process.exit(EXIT.SCHEMA_MISSING);
let subjectDigest = d.sha256 || d.sha || d.digest;
if (typeof subjectDigest !== 'string') subjectDigest = d.sha256;
if (!subjectDigest || typeof subjectDigest !== 'string') process.exit(EXIT.SCHEMA_MISSING);
subjectDigest = subjectDigest.replace(/^sha256:/i, '').trim();

const digestVal = digest.sha || digest.digest || digest.sha256;
if (typeof digestVal !== 'string') process.exit(EXIT.DIGEST_MISMATCH);
const normalizedDigest = digestVal.replace(/^sha256:/i, '').trim();
if (subjectDigest !== normalizedDigest) process.exit(EXIT.DIGEST_MISMATCH);

// Link: subject must have name (manifest/bundle identifier)
const name = first.name;
if (typeof name !== 'string' || !name.trim()) process.exit(EXIT.LINK_MISSING);
process.exit(0);
" "$ARTIFACT_PROVENANCE_PATH" "$ARTIFACT_DIGEST_PATH" 2>/dev/null
rc=$?
set -e
if [ "$rc" -eq 10 ]; then
  echo "ERROR_CODE=ARTIFACT_PROVENANCE_INVALID"
  echo "HIT_PATH=$ARTIFACT_PROVENANCE_PATH"
  exit 1
fi
if [ "$rc" -eq 11 ]; then
  echo "ERROR_CODE=ARTIFACT_PROVENANCE_SUBJECT_MISSING"
  echo "HIT_PATH=$ARTIFACT_PROVENANCE_PATH"
  exit 1
fi
if [ "$rc" -eq 12 ]; then
  echo "ERROR_CODE=ARTIFACT_PROVENANCE_SUBJECT_MISMATCH"
  echo "HIT_PATH=$ARTIFACT_DIGEST_PATH"
  exit 1
fi
if [ "$rc" -eq 13 ]; then
  echo "ERROR_CODE=ARTIFACT_PROVENANCE_LINK_MISSING"
  echo "HIT_PATH=$ARTIFACT_PROVENANCE_PATH"
  exit 1
fi
if [ "$rc" -ne 0 ]; then
  echo "ERROR_CODE=ARTIFACT_BUNDLE_PROVENANCE_LINK_UNEXPECTED_RC"
  echo "HIT_RC=$rc"
  exit 1
fi

ARTIFACT_PROVENANCE_SUBJECT_MATCH_OK=1
ARTIFACT_BUNDLE_PROVENANCE_POLICY_V1_OK=1
exit 0
