#!/usr/bin/env bash
set -euo pipefail

ARTIFACT_BUNDLE_CHAIN_STRICT_POLICY_V1_OK=0
ARTIFACT_BUNDLE_CHAIN_STRICT_ENFORCE_OK=0
ARTIFACT_BUNDLE_CHAIN_STRICT_FAILCLOSED_OK=0
trap 'echo "ARTIFACT_BUNDLE_CHAIN_STRICT_POLICY_V1_OK=${ARTIFACT_BUNDLE_CHAIN_STRICT_POLICY_V1_OK}"; echo "ARTIFACT_BUNDLE_CHAIN_STRICT_ENFORCE_OK=${ARTIFACT_BUNDLE_CHAIN_STRICT_ENFORCE_OK}"; echo "ARTIFACT_BUNDLE_CHAIN_STRICT_FAILCLOSED_OK=${ARTIFACT_BUNDLE_CHAIN_STRICT_FAILCLOSED_OK}"' EXIT

ENFORCE="${ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_ENFORCE:-0}"
if [ "$ENFORCE" != "1" ]; then
  echo "ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_SKIPPED=1"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_V1.md"
if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_WIRING_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
fi
grep -q 'ARTIFACT_BUNDLE_CHAIN_STRICT_MODE_V1_TOKEN=1' "$SSOT" || {
  echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_WIRING_MISSING"
  echo "HIT_PATH=$SSOT"
  exit 1
}

ANCHOR_PATH="scripts/verify/verify_repo_contracts.sh"
if grep -qE '^ANCHOR_PATH=' "$SSOT" 2>/dev/null; then
  ANCHOR_PATH="$(grep -E '^ANCHOR_PATH=' "$SSOT" | head -n1 | sed 's/^ANCHOR_PATH=//' | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi
if [ ! -f "$ANCHOR_PATH" ]; then
  echo "ERROR_CODE=ARTIFACT_CHAIN_STRICT_WIRING_MISSING"
  echo "HIT_PATH=$ANCHOR_PATH"
  exit 1
fi

node - "$ANCHOR_PATH" <<'NODESCRIPT'
'use strict';
const { parseRunGuardLines } = require('./tools/verify-runtime/anchor_parser_v1.cjs');
const { EXIT } = require('./tools/verify-runtime/exit_codes_v1.cjs');
const fs = require('fs');

const anchorPath = process.argv[2];
const allLines = fs.readFileSync(anchorPath, 'utf8').split('\n');
const rows = parseRunGuardLines(anchorPath);

const CHAIN = [
  { script: 'scripts/verify/verify_tuf_min_signing_chain_v1.sh',            enforceVar: 'TUF_MIN_SIGNING_CHAIN_ENFORCE' },
  { script: 'scripts/verify/verify_sbom_from_artifacts_v1.sh',              enforceVar: 'SBOM_FROM_ARTIFACTS_ENFORCE' },
  { script: 'scripts/verify/verify_artifact_manifest_bind_v1.sh',           enforceVar: 'ARTIFACT_MANIFEST_BIND_ENFORCE' },
  { script: 'scripts/verify/verify_artifact_bundle_integrity_v1.sh',        enforceVar: 'ARTIFACT_BUNDLE_INTEGRITY_ENFORCE' },
  { script: 'scripts/verify/verify_artifact_bundle_provenance_link_v1.sh',  enforceVar: 'ARTIFACT_BUNDLE_PROVENANCE_LINK_ENFORCE' },
  { script: 'scripts/verify/verify_artifact_bundle_verifier_chain_v1.sh',   enforceVar: 'ARTIFACT_BUNDLE_VERIFIER_CHAIN_ENFORCE' },
];

for (var ci = 0; ci < CHAIN.length; ci++) {
  var script = CHAIN[ci].script;
  var enforceVar = CHAIN[ci].enforceVar;

  var row = null;
  for (var ri = 0; ri < rows.length; ri++) {
    if (rows[ri].script_path === script) { row = rows[ri]; break; }
  }
  if (!row) {
    process.stdout.write('ERROR_CODE=ARTIFACT_CHAIN_STRICT_WIRING_MISSING\n');
    process.stdout.write('HIT_SCRIPT=' + script + '\n');
    process.exit(EXIT.CHAIN_ORDER_INVALID);
  }

  // Inspect context by line_number — no grep/substring file search
  var lineIdx = row.line_number - 1;
  var contextLines = allLines.slice(Math.max(0, lineIdx - 1), lineIdx + 1).join('\n');

  if (contextLines.indexOf(enforceVar) === -1) {
    process.stdout.write('ERROR_CODE=ARTIFACT_CHAIN_STRICT_ENFORCE_MISSING\n');
    process.stdout.write('HIT_SCRIPT=' + script + '\n');
    process.exit(EXIT.CHAIN_ORDER_INVALID);
  }

  // Fail-open: hardcoded ENFORCE=0 (not :-0 default) is forbidden
  var escapedVar = enforceVar.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  var failOpenRe = new RegExp('(?:^|[^:])' + escapedVar + '=0([^0-9]|$)');
  if (failOpenRe.test(contextLines)) {
    process.stdout.write('ERROR_CODE=ARTIFACT_CHAIN_STRICT_FAILOPEN_DETECTED\n');
    process.stdout.write('HIT_SCRIPT=' + script + '\n');
    process.exit(EXIT.CHAIN_ORDER_INVALID);
  }
}

process.exit(0);
NODESCRIPT
rc=$?
[ $rc -eq 0 ] || exit 1

ARTIFACT_BUNDLE_CHAIN_STRICT_ENFORCE_OK=1
ARTIFACT_BUNDLE_CHAIN_STRICT_FAILCLOSED_OK=1
ARTIFACT_BUNDLE_CHAIN_STRICT_POLICY_V1_OK=1
exit 0
