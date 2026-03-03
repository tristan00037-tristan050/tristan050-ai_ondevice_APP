#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
SSOT="docs/ops/contracts/MODEL_PACK_SBOM_CYCLONEDX_SSOT_V1.txt"
[ -f "$SSOT" ] || { echo "ERROR_CODE=SSOT_MISSING"; exit 1; }
grep -q '^MODEL_PACK_SBOM_CYCLONEDX_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=SSOT_INVALID"; exit 1; }

SBOM_OUT_PATH="$(grep -E '^SBOM_OUT_PATH=' "$SSOT" | head -n1 | sed 's/^SBOM_OUT_PATH=//' | tr -d '\r')"
[ -n "$SBOM_OUT_PATH" ] || { echo "ERROR_CODE=SSOT_INVALID"; exit 1; }

OUT_DIR="$(dirname "$SBOM_OUT_PATH")"
mkdir -p "$OUT_DIR"

node -e "
const fs = require('fs');
const path = process.argv[1];
const repo = process.env.GITHUB_REPOSITORY || 'local';
const sha = process.env.GITHUB_SHA || require('child_process').execSync('git rev-parse HEAD', { encoding: 'utf8' }).trim();
const out = {
  bomFormat: 'CycloneDX',
  specVersion: '1.4',
  version: 1,
  metadata: {
    timestamp: new Date().toISOString(),
    tools: [{ vendor: 'repo', name: 'gen_model_pack_sbom_cyclonedx_v1', version: '1' }]
  },
  components: [
    { type: 'library', name: 'model-pack', version: '0.0.0', description: 'Model pack SBOM placeholder' }
  ]
};
fs.writeFileSync(path, JSON.stringify(out, null, 2));
" "$SBOM_OUT_PATH"

echo "MODEL_PACK_SBOM_GENERATED=1"
