#!/usr/bin/env bash
set -euo pipefail

ALGO_APPLY_FAILCLOSED_E2E_OK=0
ALGO_APPLY_STATE_UNCHANGED_OK=0
ALGO_APPLY_REASON_CODE_PRESERVED_OK=0

cleanup() {
  echo "ALGO_APPLY_FAILCLOSED_E2E_OK=${ALGO_APPLY_FAILCLOSED_E2E_OK}"
  echo "ALGO_APPLY_STATE_UNCHANGED_OK=${ALGO_APPLY_STATE_UNCHANGED_OK}"
  echo "ALGO_APPLY_REASON_CODE_PRESERVED_OK=${ALGO_APPLY_REASON_CODE_PRESERVED_OK}"
  if [[ "${ALGO_APPLY_FAILCLOSED_E2E_OK}" == "1" ]] && \
     [[ "${ALGO_APPLY_STATE_UNCHANGED_OK}" == "1" ]] && \
     [[ "${ALGO_APPLY_REASON_CODE_PRESERVED_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

GOOD_DIR="model_packs/accounting_v0"
BAD_DIR="model_packs/_bad_signature_invalid"

test -s "${GOOD_DIR}/pack.json"
test -s "${GOOD_DIR}/manifest.json"
test -s "${BAD_DIR}/pack.json" || true
test -s "${BAD_DIR}/manifest.json" || true

APPLY_MOD="webcore_appcore_starter_4_17/packages/butler-runtime/src/model_pack/apply_model_pack.mjs"
test -s "$APPLY_MOD"

TMP_DIR="$(mktemp -d)"
STATE_PATH="${TMP_DIR}/active_pack_state.json"

# Create a temporary Node.js script file
NODE_SCRIPT="${TMP_DIR}/verify_apply_e2e.mjs"
cat > "$NODE_SCRIPT" <<NODE
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const statePath = process.argv[2];
const goodDir = process.argv[3];
const badDir = process.argv[4];
const ROOT = process.argv[5];

const applyModulePath = path.join(ROOT, "webcore_appcore_starter_4_17/packages/butler-runtime/src/model_pack/apply_model_pack.mjs");
const { applyModelPackOrBlock } = await import("file://" + applyModulePath);

function sha256Hex(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function readJson(p) { return JSON.parse(fs.readFileSync(p, "utf8")); }

function packIdFromDir(dir) {
  try {
    const p = readJson(path.join(ROOT, dir, "pack.json"));
    return p.pack_id ?? p.id ?? p.name ?? path.basename(dir);
  } catch {
    return path.basename(dir);
  }
}

function manifestShaFromDir(dir) {
  const m = fs.readFileSync(path.join(ROOT, dir, "manifest.json"), "utf8");
  return sha256Hex(Buffer.from(m, "utf8"));
}

function readStateBytes(p) {
  return fs.existsSync(p) ? fs.readFileSync(p) : Buffer.from("");
}

// 0) before snapshot
const beforeBytes = readStateBytes(statePath);

// 1) good apply => state must change
const goodPackId = packIdFromDir(goodDir);
const goodManifestSha = manifestShaFromDir(goodDir);
const goodPackJson = readJson(path.join(ROOT, goodDir, "pack.json"));

const r1 = applyModelPackOrBlock({
  verified: true,
  verify_reason_code: "APPLY_OK",
  pack_id: goodPackId,
  manifest_sha256: goodManifestSha,
  expires_at_ms: Date.now() + 3600_000,
  now_ms: Date.now(),
  state_path: statePath,
  compat: goodPackJson.compat,
  runtime_semver: "0.1.0",
  gateway_semver: "0.1.0",
});

if (r1.applied !== true) throw new Error("GOOD_APPLY_NOT_APPLIED");
const afterGoodBytes = readStateBytes(statePath);
if (afterGoodBytes.length === 0) throw new Error("GOOD_STATE_EMPTY");
if (Buffer.compare(beforeBytes, afterGoodBytes) === 0) throw new Error("GOOD_STATE_NOT_CHANGED");

// 2) bad apply => state must NOT change + applied=false + reason_code preserved
// bad signature scenario -> verified=false
const snapshotBytes = Buffer.from(afterGoodBytes);

const r2 = applyModelPackOrBlock({
  verified: false,
  verify_reason_code: "SIGNATURE_INVALID",
  pack_id: packIdFromDir(badDir),
  manifest_sha256: "na",
  expires_at_ms: Date.now() + 3600_000,
  now_ms: Date.now(),
  state_path: statePath,
});

if (r2.applied !== false) throw new Error("BAD_APPLY_SHOULD_BE_BLOCKED");
if (r2.reason_code !== "SIGNATURE_INVALID") throw new Error("BAD_REASON_CODE_NOT_PRESERVED");

const afterBadBytes = readStateBytes(statePath);
if (Buffer.compare(snapshotBytes, afterBadBytes) !== 0) throw new Error("BAD_STATE_CHANGED");

// 3) compat 필드 누락 => verified=true, compat은 존재하지만 runtime_semver/gateway_semver 누락 -> applied=false, state unchanged
const compatMissingSnapshotBytes = Buffer.from(afterBadBytes);

const r3 = applyModelPackOrBlock({
  verified: true,
  verify_reason_code: "APPLY_OK",
  pack_id: goodPackId,
  manifest_sha256: goodManifestSha,
  expires_at_ms: Date.now() + 3600_000,
  now_ms: Date.now(),
  state_path: statePath,
  compat: goodPackJson.compat,
  runtime_semver: undefined,
  gateway_semver: "0.1.0",
});

if (r3.applied !== false) throw new Error("COMPAT_MISSING_SHOULD_BE_BLOCKED");
if (r3.reason_code !== "MODEL_PACK_COMPAT_SEMVER_INVALID") throw new Error("COMPAT_MISSING_REASON_CODE_NOT_PRESERVED");

const afterCompatMissingBytes = readStateBytes(statePath);
if (Buffer.compare(compatMissingSnapshotBytes, afterCompatMissingBytes) !== 0) throw new Error("COMPAT_MISSING_STATE_CHANGED");

console.log("ALGO_APPLY_FAILCLOSED_E2E_OK=1");
console.log("ALGO_APPLY_STATE_UNCHANGED_OK=1");
console.log("ALGO_APPLY_REASON_CODE_PRESERVED_OK=1");
NODE

OUT=$(node "$NODE_SCRIPT" "$STATE_PATH" "$GOOD_DIR" "$BAD_DIR" "$ROOT" 2>&1) || { echo "BLOCK: node e2e failed"; echo "$OUT"; rm -f "$NODE_SCRIPT"; rm -rf "$TMP_DIR"; exit 1; }
rm -f "$NODE_SCRIPT"

echo "$OUT" | grep -q "ALGO_APPLY_FAILCLOSED_E2E_OK=1" && ALGO_APPLY_FAILCLOSED_E2E_OK=1
echo "$OUT" | grep -q "ALGO_APPLY_STATE_UNCHANGED_OK=1" && ALGO_APPLY_STATE_UNCHANGED_OK=1
echo "$OUT" | grep -q "ALGO_APPLY_REASON_CODE_PRESERVED_OK=1" && ALGO_APPLY_REASON_CODE_PRESERVED_OK=1
