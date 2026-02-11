#!/usr/bin/env bash
set -euo pipefail

FINGERPRINT_INPUT_POLICY_V1_OK=0
FINGERPRINT_INPUT_POLICY_ENFORCED_V1_OK=0
trap 'echo "FINGERPRINT_INPUT_POLICY_V1_OK=$FINGERPRINT_INPUT_POLICY_V1_OK"; echo "FINGERPRINT_INPUT_POLICY_ENFORCED_V1_OK=$FINGERPRINT_INPUT_POLICY_ENFORCED_V1_OK"' EXIT

# 1) 문서 토큰 확인 (fail-closed)
doc="docs/ops/contracts/FINGERPRINT_INPUT_POLICY_V1.md"
[ -f "$doc" ] || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "FINGERPRINT_INPUT_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }
FINGERPRINT_INPUT_POLICY_V1_OK=1

# 2) 런타임 enforcement 실증 (금지키 넣으면 반드시 throw)
command -v node >/dev/null 2>&1 || { echo "BLOCK: node missing"; exit 1; }

node - <<'NODE'
const { assertNoPerRequestKeysV1 } = require("./packages/common/meta_only/fingerprint_input_guard_v1.cjs");

const bad = { request_id: "x", a: 1 };
try {
  assertNoPerRequestKeysV1(bad);
  console.error("BLOCK: banned key passed");
  process.exit(1);
} catch (e) {
  const code = e && (e.code || e.message) ? String(e.code || e.message) : "";
  // code-only reason check
  if (!code.includes("FP_INPUT_BANNED_KEY_V1")) {
    console.error("BLOCK: wrong error code");
    process.exit(1);
  }
  process.exit(0);
}
NODE

FINGERPRINT_INPUT_POLICY_ENFORCED_V1_OK=1
exit 0
