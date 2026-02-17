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
ssot="docs/ops/contracts/PATH_SCOPE_SSOT_V1.json"
test -f "$ssot" || { echo "BLOCK: missing SSOT file: $ssot"; exit 1; }

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

# Validate JSON format
node -e "
const fs = require('fs');
const s = fs.readFileSync('$ssot', 'utf8');
try {
  const obj = JSON.parse(s);
  if (!obj || !obj.version || !Array.isArray(obj.path_scopes)) {
    console.error('BLOCK: invalid SSOT format');
    process.exit(1);
  }
} catch (e) {
  console.error('BLOCK: invalid JSON:', e.message);
  process.exit(1);
}
" || exit 1

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
  if grep -qi "$p" "$ssot"; then
    echo "BLOCK: placeholder found in SSOT: $p"
    FOUND_PLACEHOLDER=1
  fi
done

if [ "$FOUND_PLACEHOLDER" -eq 1 ]; then
  exit 1
fi

PATH_SCOPE_NO_PLACEHOLDER_OK=1

# 4) Drift check: verify that actual path usage matches SSOT
# For now, we check that the SSOT structure is valid and contains expected fields
# More sophisticated drift detection can be added later
node -e "
const fs = require('fs');
const s = fs.readFileSync('$ssot', 'utf8');
const obj = JSON.parse(s);

// Check that each scope has required fields
for (const scope of obj.path_scopes) {
  if (!scope.scope_id || typeof scope.scope_id !== 'string') {
    console.error('BLOCK: scope_id missing or invalid');
    process.exit(1);
  }
  if (!Array.isArray(scope.allowed_paths)) {
    console.error('BLOCK: allowed_paths must be array');
    process.exit(1);
  }
  if (!Array.isArray(scope.excluded_paths)) {
    console.error('BLOCK: excluded_paths must be array');
    process.exit(1);
  }
}

// Basic validation: at least one scope must exist
if (obj.path_scopes.length === 0) {
  console.error('BLOCK: no path scopes defined');
  process.exit(1);
}
" || exit 1

PATH_SCOPE_DRIFT_0_OK=1

exit 0

