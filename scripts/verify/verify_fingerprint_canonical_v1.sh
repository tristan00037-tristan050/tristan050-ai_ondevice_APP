#!/usr/bin/env bash
set -euo pipefail

AI_FINGERPRINT_CANONICAL_V1_OK=0
AI_FINGERPRINT_KEY_ORDER_INVARIANT_OK=0
trap 'echo "AI_FINGERPRINT_CANONICAL_V1_OK=$AI_FINGERPRINT_CANONICAL_V1_OK"; echo "AI_FINGERPRINT_KEY_ORDER_INVARIANT_OK=$AI_FINGERPRINT_KEY_ORDER_INVARIANT_OK"' EXIT

# require node (판정만, 설치 금지)
command -v node >/dev/null 2>&1 || { echo "BLOCK: node missing"; exit 1; }

node - <<'NODE'
const crypto = require("crypto");
const { canonicalizeMetaRecordV1 } = require("./packages/common/meta_only/canonicalize_v1.cjs");

// same content, different key order
const a = {b: 2, a: 1, c: {y: "2", x: "1"}};
const b = {c: {x: "1", y: "2"}, a: 1, b: 2};

const ca = canonicalizeMetaRecordV1(a);
const cb = canonicalizeMetaRecordV1(b);

const ha = crypto.createHash("sha256").update(ca).digest("hex");
const hb = crypto.createHash("sha256").update(cb).digest("hex");

if (ha !== hb) {
  console.error("BLOCK: KEY_ORDER_CHANGED_FINGERPRINT");
  process.exit(1);
}
process.exit(0);
NODE

AI_FINGERPRINT_CANONICAL_V1_OK=1
AI_FINGERPRINT_KEY_ORDER_INVARIANT_OK=1
exit 0
