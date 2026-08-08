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
INPUT_REPORTS_ROOT="${AUTODECISION_INPUT_REPORTS_ROOT:-${AUTODECISION_REPORTS_ROOT:-docs/ops/reports}}"
OUTPUT_REPORTS_ROOT="${AUTODECISION_OUTPUT_REPORTS_ROOT:-}"
EVIDENCE_ROOT="${AC25_EVIDENCE_ROOT:-}"

if [[ -n "$EVIDENCE_ROOT" ]]; then
  [[ -n "$OUTPUT_REPORTS_ROOT" ]] || { echo "ERROR_CODE=AUTODECISION_OUTPUT_ROOT_REQUIRED"; exit 1; }
elif [[ -n "${AUTODECISION_REPORTS_ROOT:-}" ]]; then
  OUTPUT_REPORTS_ROOT="$AUTODECISION_REPORTS_ROOT"
else
  if [[ -n "${RUNNER_TEMP:-}" ]]; then
    install -d -m 0700 -- "$RUNNER_TEMP"
    EVIDENCE_ROOT="$(mktemp -d "$RUNNER_TEMP/autodecision-v46.XXXXXX")"
  else
    EVIDENCE_ROOT="$(mktemp -d)"
  fi
  chmod 0700 -- "$EVIDENCE_ROOT"
  OUTPUT_REPORTS_ROOT="$EVIDENCE_ROOT/autodecision"
fi

if [[ -n "$EVIDENCE_ROOT" ]]; then
  install -d -m 0700 -- "$OUTPUT_REPORTS_ROOT"
  EVIDENCE_ROOT="$(cd "$EVIDENCE_ROOT" && pwd -P)"
  OUTPUT_REPORTS_ROOT="$(cd "$OUTPUT_REPORTS_ROOT" && pwd -P)"
fi

out_json="$OUTPUT_REPORTS_ROOT/autodecision_latest.json"
out_md="$OUTPUT_REPORTS_ROOT/autodecision_latest.md"

test -f "$policy" || { echo "ERROR_CODE=AUTODECISION_POLICY_MISSING"; exit 1; }
grep -q "AUTODECISION_POLICY_V1_TOKEN=1" "$policy" || { echo "ERROR_CODE=AUTODECISION_POLICY_TOKEN_MISSING"; exit 1; }
test -f "$gen" || { echo "ERROR_CODE=AUTODECISION_GENERATOR_MISSING"; exit 1; }

AUTODECISION_POLICY_V1_OK=1

# 항상 최신 입력 기준으로 재생성 (stale 방지). AC25에서는 입력과 출력
# root를 분리하며 저장소 내부 fallback을 허용하지 않는다.
AUTODECISION_INPUT_REPORTS_ROOT="$INPUT_REPORTS_ROOT" \
AUTODECISION_OUTPUT_REPORTS_ROOT="$OUTPUT_REPORTS_ROOT" \
AC25_EVIDENCE_ROOT="$EVIDENCE_ROOT" \
node "$gen"

test -f "$out_json" || { echo "ERROR_CODE=AUTODECISION_JSON_MISSING"; exit 1; }
test -s "$out_json" || { echo "ERROR_CODE=AUTODECISION_JSON_EMPTY"; exit 1; }
test -f "$out_md" || { echo "ERROR_CODE=AUTODECISION_MARKDOWN_MISSING"; exit 1; }
test -s "$out_md" || { echo "ERROR_CODE=AUTODECISION_MARKDOWN_EMPTY"; exit 1; }

AUTODECISION_OUTPUT_PRESENT_OK=1

# meta-only: 긴 라인 차단(>=2000)
while IFS= read -r line || [ -n "$line" ]; do
  [ "${#line}" -ge 2000 ] && { echo "ERROR_CODE=AUTODECISION_LINE_TOO_LONG"; exit 1; }
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
