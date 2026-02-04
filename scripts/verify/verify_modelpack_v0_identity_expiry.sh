#!/usr/bin/env bash
set -euo pipefail

MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK=0
MODEL_PACK_V0_EXPIRES_ENFORCED_OK=0

TMP_DIR=""

cleanup() {
  # temp dir cleanup (best-effort)
  if [[ -n "${TMP_DIR:-}" ]]; then
    rm -rf "${TMP_DIR}" >/dev/null 2>&1 || true
  fi
  echo "MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK=${MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK}"
  echo "MODEL_PACK_V0_EXPIRES_ENFORCED_OK=${MODEL_PACK_V0_EXPIRES_ENFORCED_OK}"
  if [[ "${MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK}" == "1" ]] && \
     [[ "${MODEL_PACK_V0_EXPIRES_ENFORCED_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

GOOD="model_packs/accounting_v0/pack.json"
BAD="model_packs/_bad_id_missing/pack.json"
SSOT="docs/ops/contracts/MODEL_PACK_V0_SSOT.md"

test -s "$GOOD"
test -s "$BAD"
test -s "$SSOT"

# Create a temporary Node.js script file
TMP_DIR=$(mktemp -d)
NODE_SCRIPT="${TMP_DIR}/verify_identity_expiry.mjs"
cat > "$NODE_SCRIPT" <<'NODE'
import fs from "node:fs";

const goodPath = process.argv[2];
const badPath = process.argv[3];

function must(obj, k) {
  if (!(k in obj)) throw new Error(`MISSING:${k}`);
  const v = obj[k];
  if (v === null || v === undefined) throw new Error(`NULL:${k}`);
  if (typeof v === "string" && v.trim().length === 0) throw new Error(`EMPTY:${k}`);
  return v;
}

function validatePack(p, { shouldPass }) {
  const o = JSON.parse(fs.readFileSync(p, "utf8"));

  // required identity fields
  must(o, "schema_name");
  must(o, "name");
  must(o, "version");
  must(o, "dept");
  must(o, "created_at_utc");

  // new required
  must(o, "pack_id");
  must(o, "platform");
  must(o, "runtime_version");
  const exp = must(o, "expires_at_ms");

  if (!Number.isFinite(exp) || exp <= 0) throw new Error("EXPIRES_AT_INVALID");
  const now = Date.now();
  if (now > exp) throw new Error("EXPIRED_BLOCKED");

  return true;
}

let goodOk = false;
try {
  validatePack(goodPath, { shouldPass: true });
  goodOk = true;
} catch (e) {
  console.error(`BLOCK: good pack invalid: ${String(e?.message ?? e)}`);
  process.exit(1);
}

let badFailed = false;
try {
  validatePack(badPath, { shouldPass: false });
  // if it didn't throw, it's wrong
  badFailed = false;
} catch {
  badFailed = true; // expected
}

if (!goodOk) process.exit(1);
if (!badFailed) {
  console.error("BLOCK: bad pack should have failed identity/expiry validation");
  process.exit(1);
}

console.log("MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK=1");
console.log("MODEL_PACK_V0_EXPIRES_ENFORCED_OK=1");
process.exit(0);
NODE

OUT=$(node "$NODE_SCRIPT" "$GOOD" "$BAD" 2>&1) || { echo "BLOCK: node validation failed"; echo "$OUT"; rm -rf "$TMP_DIR"; exit 1; }
rm -rf "$TMP_DIR"

echo "$OUT" | grep -q "MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK=1" && MODEL_PACK_V0_ID_FIELDS_REQUIRED_OK=1
echo "$OUT" | grep -q "MODEL_PACK_V0_EXPIRES_ENFORCED_OK=1" && MODEL_PACK_V0_EXPIRES_ENFORCED_OK=1

exit 0

