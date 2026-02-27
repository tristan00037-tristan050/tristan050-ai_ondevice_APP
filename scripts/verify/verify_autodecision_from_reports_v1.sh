#!/usr/bin/env bash
set -euo pipefail

AUTODECISION_POLICY_V1_OK=0
AUTODECISION_OUTPUT_PRESENT_OK=0
AUTODECISION_REASON_CODE_ONLY_OK=0

trap 'echo "AUTODECISION_POLICY_V1_OK=$AUTODECISION_POLICY_V1_OK";
      echo "AUTODECISION_OUTPUT_PRESENT_OK=$AUTODECISION_OUTPUT_PRESENT_OK";
      echo "AUTODECISION_REASON_CODE_ONLY_OK=$AUTODECISION_REASON_CODE_ONLY_OK"' EXIT

policy="docs/ops/contracts/AUTODECISION_POLICY_V1.md"
gen="scripts/ops/gen_autodecision_v1.mjs"
REPORTS_ROOT="${AUTODECISION_REPORTS_ROOT:-docs/ops/reports}"
out_json="$REPORTS_ROOT/autodecision_latest.json"
out_md="$REPORTS_ROOT/autodecision_latest.md"

test -f "$policy" || { echo "BLOCK: missing $policy"; exit 1; }
grep -q "AUTODECISION_POLICY_V1_TOKEN=1" "$policy" || { echo "BLOCK: missing token"; exit 1; }
test -f "$gen" || { echo "BLOCK: missing $gen"; exit 1; }

AUTODECISION_POLICY_V1_OK=1

# 항상 최신 입력 기준으로 재생성 (stale 방지)
node "$gen"

test -f "$out_json" || { echo "BLOCK: missing $out_json"; exit 1; }
test -s "$out_json" || { echo "BLOCK: empty $out_json"; exit 1; }
test -f "$out_md" || { echo "BLOCK: missing $out_md"; exit 1; }
test -s "$out_md" || { echo "BLOCK: empty $out_md"; exit 1; }

AUTODECISION_OUTPUT_PRESENT_OK=1

# meta-only: 긴 라인 차단(>=2000)
while IFS= read -r line || [ -n "$line" ]; do
  [ "${#line}" -ge 2000 ] && { echo "BLOCK: long line in autodecision json"; exit 1; }
done < "$out_json"

# reason_codes는 키 이름만(대문자/숫자/_)로 제한
AUTODECISION_JSON_PATH="$out_json" node - <<'NODE'
const fs = require('fs');
const p = JSON.parse(fs.readFileSync(process.env.AUTODECISION_JSON_PATH || 'docs/ops/reports/autodecision_latest.json','utf8'));
if (!p || typeof p !== 'object') process.exit(2);
if (!Array.isArray(p.reason_codes)) process.exit(2);
for (const r of p.reason_codes) {
  if (typeof r !== 'string') process.exit(2);
  if (!/^[A-Z0-9_]+$/.test(r)) process.exit(2);
}
process.exit(0);
NODE

AUTODECISION_REASON_CODE_ONLY_OK=1
exit 0
