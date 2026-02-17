#!/usr/bin/env bash
set -euo pipefail

PATH_SCOPE_SSOT_PRESENT_OK=0
PATH_SCOPE_NO_PLACEHOLDER_OK=0
PATH_SCOPE_DRIFT_0_OK=0

cleanup() {
  echo "PATH_SCOPE_SSOT_PRESENT_OK=${PATH_SCOPE_SSOT_PRESENT_OK}"
  echo "PATH_SCOPE_NO_PLACEHOLDER_OK=${PATH_SCOPE_NO_PLACEHOLDER_OK}"
  echo "PATH_SCOPE_DRIFT_0_OK=${PATH_SCOPE_DRIFT_0_OK}"

  if [[ "$PATH_SCOPE_SSOT_PRESENT_OK" == "1" ]] && \
     [[ "$PATH_SCOPE_NO_PLACEHOLDER_OK" == "1" ]] && \
     [[ "$PATH_SCOPE_DRIFT_0_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# 1) Policy document check
doc="docs/ops/contracts/PATH_SCOPE_POLICY_V1.md"
test -f "$doc" || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "PATH_SCOPE_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

# 2) SSOT file existence and format
SSOT="docs/ops/contracts/PATH_SCOPE_SSOT_V1.json"
test -f "$SSOT" || { echo "BLOCK: missing SSOT file: $SSOT"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

# Validate JSON format and structure
node - <<'NODE'
const fs = require('fs');
const ssot = JSON.parse(fs.readFileSync('docs/ops/contracts/PATH_SCOPE_SSOT_V1.json','utf8'));
if (!Array.isArray(ssot.allowed_paths) || !Array.isArray(ssot.excluded_paths)) {
  console.error('BLOCK: invalid SSOT format (allowed_paths/excluded_paths must be arrays)');
  process.exit(2);
}
NODE
[ $? -eq 0 ] || exit 1

PATH_SCOPE_SSOT_PRESENT_OK=1

# 3) Check for placeholder values
PLACEHOLDERS=(
  "PLACEHOLDER"
  "TODO"
  "FIXME"
  "XXX"
  "TBD"
  "REPLACE_ME"
)

FOUND_PLACEHOLDER=0
for p in "${PLACEHOLDERS[@]}"; do
  if grep -qi "$p" "$SSOT"; then
    echo "BLOCK: placeholder found in SSOT: $p"
    FOUND_PLACEHOLDER=1
  fi
done

if [ "$FOUND_PLACEHOLDER" -eq 1 ]; then
  exit 1
fi

PATH_SCOPE_NO_PLACEHOLDER_OK=1

# 4) Drift check: compare actual path usage against SSOT
have_rg() { command -v rg >/dev/null 2>&1; }

extract_paths() {
  if have_rg; then
    rg -oN '(?<![A-Za-z0-9_./-])(\.github/[^"'\''\s)]+|docs/[^"'\''\s)]+|scripts/[^"'\''\s)]+|webcore_appcore_starter_4_17/[^"'\''\s)]+)' \
      .github/workflows scripts/verify 2>/dev/null \
      | awk -F: '{print $NF}' | sort -u
  else
    # 단순 패턴(정확도 낮지만 fail-closed 방지용)
    grep -RhoE '(\.github/[^"'\''[:space:])]+|docs/[^"'\''[:space:])]+|scripts/[^"'\''[:space:])]+|webcore_appcore_starter_4_17/[^"'\''[:space:])]+)' \
      .github/workflows scripts/verify 2>/dev/null \
      | sort -u
  fi
}

PATHS="$(extract_paths || true)"

echo "$PATHS" | node - <<'NODE'
const fs = require('fs');
const path = require('path');

const ssot = JSON.parse(fs.readFileSync('docs/ops/contracts/PATH_SCOPE_SSOT_V1.json','utf8'));
const allowed = ssot.allowed_paths.map(p=>p.replace(/\/+$/,''));
const excluded = ssot.excluded_paths.map(p=>p.replace(/\/+$/,''));

function isUnder(x, root) {
  x = x.replace(/\\/g,'/').replace(/\/+$/,'');
  root = root.replace(/\\/g,'/').replace(/\/+$/,'');
  return x === root || x.startsWith(root + '/');
}

const lines = require('fs').readFileSync(0,'utf8').split('\n').map(s=>s.trim()).filter(Boolean);

let bad = [];
for (const p of lines) {
  const norm = p.replace(/\\/g,'/');
  // excluded 우선
  if (excluded.some(ex => isUnder(norm, ex))) {
    bad.push(`BLOCK: path hits excluded_paths: ${p}`);
    continue;
  }
  // allowed 아래인지
  if (!allowed.some(al => isUnder(norm, al))) {
    bad.push(`BLOCK: path outside allowed_paths: ${p}`);
  }
}

if (bad.length) {
  console.error(bad.join('\n'));
  process.exit(1);
}

process.exit(0);
NODE

[ $? -eq 0 ] || exit 1

PATH_SCOPE_DRIFT_0_OK=1

exit 0
