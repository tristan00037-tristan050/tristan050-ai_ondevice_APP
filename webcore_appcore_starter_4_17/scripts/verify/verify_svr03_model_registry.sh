#!/usr/bin/env bash
set -euo pipefail

# SVR-03-B: Signed Artifact Delivery v1 (fail-closed)
# Evidence sealing script for model registry signing verification
# Uses npm only for test execution

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Pre-gate: canonicalization single-source guard
# Find repo root (may be webcore_appcore_starter_4_17 or parent)
REPO_ROOT="$ROOT"
if [[ -d "${ROOT}/webcore_appcore_starter_4_17" ]]; then
  REPO_ROOT="${ROOT}/webcore_appcore_starter_4_17/.."
  REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
fi
if [[ -f "${REPO_ROOT}/scripts/verify/verify_canonicalization_single_source.sh" ]]; then
  bash "${REPO_ROOT}/scripts/verify/verify_canonicalization_single_source.sh"
elif [[ -f "${ROOT}/../scripts/verify/verify_canonicalization_single_source.sh" ]]; then
  bash "${ROOT}/../scripts/verify/verify_canonicalization_single_source.sh"
else
  echo "WARN: verify_canonicalization_single_source.sh not found, skipping"
fi

# Initialize evidence flags
MODEL_UPLOAD_SIGN_VERIFY_OK=0
MODEL_DELIVERY_SIGNATURE_REQUIRED_OK=0
MODEL_APPLY_FAILCLOSED_OK=0
MODEL_ROLLBACK_OK=0

# Note: Evidence keys are now set by Node.js JSON parser, not in cleanup
# cleanup trap removed - exit codes are handled directly

# Guard: Forbid "OK=1" in tests
if [[ -d "${ROOT}/webcore_appcore_starter_4_17" ]]; then
  TEST_DIR="${ROOT}/webcore_appcore_starter_4_17/backend/model_registry/tests"
  MODEL_REGISTRY_DIR="${ROOT}/webcore_appcore_starter_4_17/backend/model_registry"
else
  TEST_DIR="${ROOT}/backend/model_registry/tests"
  MODEL_REGISTRY_DIR="${ROOT}/backend/model_registry"
fi

if command -v rg >/dev/null 2>&1; then
  OK1_MATCHES=$(rg -n "OK=1" "${TEST_DIR}" 2>/dev/null || true)
  if [[ -n "$OK1_MATCHES" ]]; then
    echo "FAIL: 'OK=1' found in tests:"
    echo "$OK1_MATCHES"
    exit 1
  fi
elif command -v grep >/dev/null 2>&1; then
  if grep -r "OK=1" "${TEST_DIR}" 2>/dev/null | grep -v "^$"; then
    echo "FAIL: 'OK=1' found in tests"
    exit 1
  fi
fi

# Check Node.js and npm availability
command -v node >/dev/null 2>&1 || { echo "FAIL: node not found"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "FAIL: npm not found"; exit 1; }

# Run tests using npm only (model_registry package only)
if [[ ! -d "$MODEL_REGISTRY_DIR" ]]; then
  echo "FAIL: model_registry directory not found: $MODEL_REGISTRY_DIR"
  exit 1
fi

# Check dependencies exist (workflow must install)

require_lockfile() {
  local dir="$1"
  if [[ ! -f "${dir}/package-lock.json" ]]; then
    echo "FAIL: lockfile missing (package-lock.json): ${dir}"
    exit 1
  fi
}

CONTROL_PLANE_DIR="${ROOT}/webcore_appcore_starter_4_17/backend/control_plane"
if [[ -d "$CONTROL_PLANE_DIR" ]]; then
  require_lockfile "$CONTROL_PLANE_DIR"
  # Check dependencies exist (workflow must install)
  test -d "${CONTROL_PLANE_DIR}/node_modules" || { echo "BLOCK: node_modules missing (workflow must install dependencies)"; exit 1; }
fi

require_lockfile "$MODEL_REGISTRY_DIR"
# Check dependencies exist (workflow must install)
test -d "${MODEL_REGISTRY_DIR}/node_modules" || { echo "BLOCK: node_modules missing (workflow must install dependencies)"; exit 1; }

# Run tests and parse results
cd "$MODEL_REGISTRY_DIR"

export RESULT_JSON="/tmp/svr03_jest_results.json"
rm -f "$RESULT_JSON"

# Run tests with JSON output (stable, no grep of human text)
set +e
npm test -- --json --outputFile "$RESULT_JSON"
TEST_EXIT=$?
set -e

# Fail-closed if jest did not produce json
if [[ ! -f "$RESULT_JSON" ]]; then
  echo "FAIL: jest json output missing: $RESULT_JSON"
  exit 1
fi

# Parse JSON and set evidence keys based on tagged test names
node <<'NODE'
const fs = require('fs');

const jsonPath = process.env.RESULT_JSON || "/tmp/svr03_jest_results.json";
const raw = fs.readFileSync(jsonPath, 'utf8');
const data = JSON.parse(raw);

const keys = [
  "MODEL_UPLOAD_SIGN_VERIFY_OK",
  "MODEL_DELIVERY_SIGNATURE_REQUIRED_OK",
  "MODEL_APPLY_FAILCLOSED_OK",
  "MODEL_ROLLBACK_OK"
];

const found = new Set();
function walk(node) {
  if (!node) return;
  if (typeof node === 'string') {
    const m = node.match(/\[EVID:([A-Z0-9_]+)\]/g);
    if (m) m.forEach(x => found.add(x.replace('[EVID:','').replace(']','')));
    return;
  }
  if (Array.isArray(node)) return node.forEach(walk);
  if (typeof node === 'object') {
    for (const k of Object.keys(node)) walk(node[k]);
  }
}

walk(data);

const out = {};
for (const k of keys) out[k] = 0;
for (const k of keys) {
  if (found.has(k)) out[k] = 1;
}

for (const k of keys) {
  console.log(`${k}=${out[k]}`);
}

// Hard rule: core 3 keys must be present
const ok = out.MODEL_UPLOAD_SIGN_VERIFY_OK && out.MODEL_DELIVERY_SIGNATURE_REQUIRED_OK && out.MODEL_APPLY_FAILCLOSED_OK;
process.exit(ok ? 0 : 1);
NODE

NODE_EXIT=$?

# If node script failed, exit with failure
if [[ "$NODE_EXIT" -ne 0 ]]; then
  exit 1
fi

# If tests failed, exit with failure
if [[ "$TEST_EXIT" -ne 0 ]]; then
  exit 1
fi
