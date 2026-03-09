#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_BUNDLE_VERIFIER_CHAIN_POLICY_V1_OK=0
ARTIFACT_BUNDLE_VERIFIER_CHAIN_PRESENT_OK=0
ARTIFACT_BUNDLE_VERIFIER_CHAIN_ORDER_OK=0
ARTIFACT_VERIFIER_CHAIN_EXEC_LINES_ONLY_OK=0
trap 'echo "ARTIFACT_BUNDLE_VERIFIER_CHAIN_POLICY_V1_OK=${ARTIFACT_BUNDLE_VERIFIER_CHAIN_POLICY_V1_OK}"; echo "ARTIFACT_BUNDLE_VERIFIER_CHAIN_PRESENT_OK=${ARTIFACT_BUNDLE_VERIFIER_CHAIN_PRESENT_OK}"; echo "ARTIFACT_BUNDLE_VERIFIER_CHAIN_ORDER_OK=${ARTIFACT_BUNDLE_VERIFIER_CHAIN_ORDER_OK}"; echo "ARTIFACT_VERIFIER_CHAIN_EXEC_LINES_ONLY_OK=${ARTIFACT_VERIFIER_CHAIN_EXEC_LINES_ONLY_OK}"' EXIT

ENFORCE="${ARTIFACT_BUNDLE_VERIFIER_CHAIN_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "ARTIFACT_BUNDLE_VERIFIER_CHAIN_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/ARTIFACT_VERIFIER_CHAIN_EXEC_LINES_ONLY_V1.txt"
[[ -f "$SSOT" ]] || { echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_EXEC_LINES_SSOT_MISSING"; exit 1; }
grep -q '^ARTIFACT_VERIFIER_CHAIN_EXEC_LINES_ONLY_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_EXEC_LINES_TOKEN_MISSING"; exit 1; }

ANCHOR_PATH="$(grep -E '^ANCHOR_PATH=' "$SSOT" | head -n1 | sed 's/^ANCHOR_PATH=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
[[ -n "$ANCHOR_PATH" ]] || { echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_ANCHOR_PATH_MISSING"; exit 1; }
ANCHOR_FULL="${ROOT}/${ANCHOR_PATH}"
[[ -f "$ANCHOR_FULL" ]] || { echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_ANCHOR_MISSING"; echo "HIT_PATH=$ANCHOR_PATH"; exit 1; }

CHAIN_1="$(grep -E '^CHAIN_1=' "$SSOT" | head -n1 | sed 's/^CHAIN_1=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
CHAIN_2="$(grep -E '^CHAIN_2=' "$SSOT" | head -n1 | sed 's/^CHAIN_2=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
CHAIN_3="$(grep -E '^CHAIN_3=' "$SSOT" | head -n1 | sed 's/^CHAIN_3=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
CHAIN_4="$(grep -E '^CHAIN_4=' "$SSOT" | head -n1 | sed 's/^CHAIN_4=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
CHAIN_5="$(grep -E '^CHAIN_5=' "$SSOT" | head -n1 | sed 's/^CHAIN_5=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
[[ -n "$CHAIN_1" && -n "$CHAIN_2" && -n "$CHAIN_3" && -n "$CHAIN_4" && -n "$CHAIN_5" ]] || { echo "ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_DEF_MISSING"; exit 1; }

VERIFIER_EXEC_MODE=eval node -e '
const { parseRunGuardLines, assertUniqueOrderedPaths } = require("./tools/verify-runtime/anchor_parser_v1.cjs");
const { getUserArg, expectUserArgsAtLeast } = require("./tools/verify-runtime/node_args_v1.cjs");
expectUserArgsAtLeast(1);
const anchorPath = getUserArg(1);
const expected = process.argv.slice(require("./tools/verify-runtime/node_args_v1.cjs").getArgOffset() + 1);

const rows = parseRunGuardLines(anchorPath);
const filtered = rows.filter(r => expected.includes(r.script_path));

for (const e of expected) {
  if (!filtered.some(r => r.script_path === e)) {
    process.stdout.write("ERROR_CODE=ARTIFACT_VERIFIER_CHAIN_MISSING\n");
    process.stdout.write("HIT_SCRIPT=" + e + "\n");
    process.exit(10);
  }
}

assertUniqueOrderedPaths(filtered, expected);
process.exit(0);
' "$ANCHOR_FULL" \
  "$CHAIN_1" "$CHAIN_2" "$CHAIN_3" "$CHAIN_4" "$CHAIN_5" || {
  rc=$?
  exit 1
}

ARTIFACT_BUNDLE_VERIFIER_CHAIN_POLICY_V1_OK=1
ARTIFACT_BUNDLE_VERIFIER_CHAIN_PRESENT_OK=1
ARTIFACT_BUNDLE_VERIFIER_CHAIN_ORDER_OK=1
ARTIFACT_VERIFIER_CHAIN_EXEC_LINES_ONLY_OK=1
exit 0
