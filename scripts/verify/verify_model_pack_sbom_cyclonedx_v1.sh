#!/usr/bin/env bash
set -euo pipefail

MODEL_PACK_SBOM_CYCLONEDX_V1_OK=0
finish() { [ "${MODEL_PACK_SBOM_CYCLONEDX_V1_OK:-0}" -eq 1 ] && echo "MODEL_PACK_SBOM_CYCLONEDX_V1_OK=1"; true; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
SSOT="docs/ops/contracts/MODEL_PACK_SBOM_CYCLONEDX_SSOT_V1.txt"

if [ ! -f "$SSOT" ]; then
  echo "ERROR_CODE=SSOT_MISSING_OR_INVALID"
  exit 1
fi
grep -q '^MODEL_PACK_SBOM_CYCLONEDX_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=SSOT_MISSING_OR_INVALID"; exit 1; }

SBOM_OUT_PATH="$(grep -E '^SBOM_OUT_PATH=' "$SSOT" | head -n1 | sed 's/^SBOM_OUT_PATH=//' | tr -d '\r')"
[ -n "$SBOM_OUT_PATH" ] || { echo "ERROR_CODE=SSOT_MISSING_OR_INVALID"; exit 1; }

# enforce flag (default: 0)
ENFORCE="${MODEL_PACK_SBOM_ENFORCE:-0}"

if [ ! -f "$SBOM_OUT_PATH" ]; then
  if [ "$ENFORCE" = "1" ]; then
    echo "ERROR_CODE=SBOM_FILE_MISSING"
    exit 1
  fi
  echo "MODEL_PACK_SBOM_CYCLONEDX_V1_SKIPPED=1"
  exit 0
fi

set +e
node -e "
const fs = require('fs');
let d;
try { d = JSON.parse(fs.readFileSync(process.argv[1], 'utf8')); } catch (e) { process.exit(1); }
if (!d || typeof d !== 'object') process.exit(1);
if (!d.bomFormat || !d.specVersion || !Array.isArray(d.components) || d.components.length < 1) process.exit(2);
" "$SBOM_OUT_PATH" 2>/dev/null
r=$?
set -e

[ "$r" -eq 0 ] && true
[ "$r" -eq 1 ] && { echo "ERROR_CODE=SBOM_JSON_INVALID"; exit 1; }
[ "$r" -eq 2 ] && { echo "ERROR_CODE=SBOM_KEYS_MISSING"; exit 1; }
[ "$r" -ne 0 ] && { echo "ERROR_CODE=SBOM_JSON_INVALID"; exit 1; }

MODEL_PACK_SBOM_CYCLONEDX_V1_OK=1
exit 0
