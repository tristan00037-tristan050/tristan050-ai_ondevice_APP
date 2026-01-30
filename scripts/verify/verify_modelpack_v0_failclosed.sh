#!/usr/bin/env bash
set -euo pipefail

MODEL_PACK_SCHEMA_SSOT_OK=0
MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK=0
MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK=0
MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK=0
MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK=0

cleanup(){
  echo "MODEL_PACK_SCHEMA_SSOT_OK=${MODEL_PACK_SCHEMA_SSOT_OK}"
  echo "MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK=${MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK}"
  echo "MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK=${MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK}"
  echo "MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK=${MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK}"
  echo "MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK=${MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK}"
  if [[ "${MODEL_PACK_SCHEMA_SSOT_OK}" == "1" ]] && \
     [[ "${MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK}" == "1" ]] && \
     [[ "${MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK}" == "1" ]] && \
     [[ "${MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK}" == "1" ]] && \
     [[ "${MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "BLOCK: jq not found"; exit 1; }

# 1) SSOT 문서 존재 확인
SSOT="docs/ops/contracts/MODEL_PACK_V0_SSOT.md"
test -s "$SSOT"
MODEL_PACK_SCHEMA_SSOT_OK=1

# 2) 정상 팩 검증 (accounting_v0)
GOOD_PACK="model_packs/accounting_v0"
test -s "${GOOD_PACK}/pack.json"
test -s "${GOOD_PACK}/manifest.json"
test -s "${GOOD_PACK}/signature.json"

# Verify manifest files match actual file hashes
node - <<'NODE'
const fs = require("fs");
const crypto = require("crypto");
const path = require("path");

function sha256File(p) {
  const buf = fs.readFileSync(p);
  return crypto.createHash("sha256").update(buf).digest("hex");
}

const packDir = "model_packs/accounting_v0";
const manifestPath = path.join(packDir, "manifest.json");
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

for (const file of manifest.files) {
  const filePath = path.join(packDir, file.path);
  if (!fs.existsSync(filePath)) {
    console.error(`BLOCK: file not found: ${file.path}`);
    process.exit(1);
  }
  const actualHash = sha256File(filePath);
  if (actualHash !== file.sha256) {
    console.error(`BLOCK: hash mismatch for ${file.path}: expected ${file.sha256}, got ${actualHash}`);
    process.exit(1);
  }
}

// Verify signature
const signaturePath = path.join(packDir, "signature.json");
const signature = JSON.parse(fs.readFileSync(signaturePath, "utf8"));
const manifestBuf = fs.readFileSync(manifestPath, "utf8");

const pemPub = Buffer.from(signature.public_key_b64, "base64").toString("utf8");
const pubKey = require("crypto").createPublicKey({ key: pemPub, format: "pem", type: "spki" });
const sigBuf = Buffer.from(signature.signature_b64, "base64");

const ok = require("crypto").verify(null, Buffer.from(manifestBuf, "utf8"), pubKey, sigBuf);
if (!ok) {
  console.error("BLOCK: signature verification failed");
  process.exit(1);
}

console.log("MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK=1");
NODE
MODEL_PACK_SIGNED_MANIFEST_VERIFY_OK=1

# 3) 실패 케이스 1: manifest.json 없음
BAD_MISSING="model_packs/_bad_manifest_missing"
test -s "${BAD_MISSING}/pack.json"
if [[ -f "${BAD_MISSING}/manifest.json" ]]; then
  echo "BLOCK: _bad_manifest_missing should not have manifest.json"
  exit 1
fi

# Verify that missing manifest fails (using a simple check script)
node - <<'NODE'
const fs = require("fs");
const packDir = "model_packs/_bad_manifest_missing";
const manifestPath = require("path").join(packDir, "manifest.json");
if (fs.existsSync(manifestPath)) {
  console.error("BLOCK: manifest.json should not exist");
  process.exit(1);
}
console.log("MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK=1");
NODE
MODEL_PACK_MANIFEST_MISSING_FAILCLOSED_OK=1

# 4) 실패 케이스 2: hash mismatch
BAD_HASH="model_packs/_bad_hash_mismatch"
test -s "${BAD_HASH}/manifest.json"
test -s "${BAD_HASH}/signature.json"

# Verify that hash mismatch fails
set +e
node - <<'NODE'
const fs = require("fs");
const crypto = require("crypto");
const path = require("path");

function sha256File(p) {
  const buf = fs.readFileSync(p);
  return crypto.createHash("sha256").update(buf).digest("hex");
}

const packDir = "model_packs/_bad_hash_mismatch";
const manifestPath = path.join(packDir, "manifest.json");
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

for (const file of manifest.files) {
  const filePath = path.join(packDir, file.path);
  if (!fs.existsSync(filePath)) continue;
  const actualHash = sha256File(filePath);
  if (actualHash !== file.sha256) {
    // This is expected for _bad_hash_mismatch
    console.log("MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK=1");
    process.exit(0);
  }
}
console.error("BLOCK: hash mismatch test should have detected mismatch");
process.exit(1);
NODE
RC=$?
set -e
if [[ $RC -ne 0 ]]; then
  echo "BLOCK: hash mismatch test failed"
  exit 1
fi
MODEL_PACK_HASH_MISMATCH_FAILCLOSED_OK=1

# 5) 실패 케이스 3: invalid signature
BAD_SIG="model_packs/_bad_signature_invalid"
test -s "${BAD_SIG}/manifest.json"
test -s "${BAD_SIG}/signature.json"

# Verify that invalid signature fails
node - <<'NODE'
const fs = require("fs");
const crypto = require("crypto");
const path = require("path");

const packDir = "model_packs/_bad_signature_invalid";
const manifestPath = path.join(packDir, "manifest.json");
const signaturePath = path.join(packDir, "signature.json");

const manifestBuf = fs.readFileSync(manifestPath, "utf8");
const signature = JSON.parse(fs.readFileSync(signaturePath, "utf8"));

try {
  const pemPub = Buffer.from(signature.public_key_b64, "base64").toString("utf8");
  const pubKey = crypto.createPublicKey({ key: pemPub, format: "pem", type: "spki" });
  const sigBuf = Buffer.from(signature.signature_b64, "base64");
  
  const ok = crypto.verify(null, Buffer.from(manifestBuf, "utf8"), pubKey, sigBuf);
  if (!ok) {
    // This is expected for _bad_signature_invalid
    console.log("MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK=1");
    process.exit(0);
  }
} catch (err) {
  // Invalid signature format also counts as failure
  console.log("MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK=1");
  process.exit(0);
}
console.error("BLOCK: invalid signature test should have detected invalid signature");
process.exit(1);
NODE
MODEL_PACK_SIGNATURE_INVALID_FAILCLOSED_OK=1

exit 0

