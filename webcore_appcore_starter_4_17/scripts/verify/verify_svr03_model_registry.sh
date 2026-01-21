#!/usr/bin/env bash
set -euo pipefail

# SVR-03-B: Signed Artifact Delivery v1 (fail-closed)
# Evidence sealing script for model registry signing verification
# Uses npm only for test execution

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# Initialize evidence flags
MODEL_UPLOAD_SIGN_VERIFY_OK=0
MODEL_DELIVERY_SIGNATURE_REQUIRED_OK=0
MODEL_APPLY_FAILCLOSED_OK=0
MODEL_ROLLBACK_OK=0

cleanup() {
  echo "MODEL_UPLOAD_SIGN_VERIFY_OK=${MODEL_UPLOAD_SIGN_VERIFY_OK}"
  echo "MODEL_DELIVERY_SIGNATURE_REQUIRED_OK=${MODEL_DELIVERY_SIGNATURE_REQUIRED_OK}"
  echo "MODEL_APPLY_FAILCLOSED_OK=${MODEL_APPLY_FAILCLOSED_OK}"
  echo "MODEL_ROLLBACK_OK=${MODEL_ROLLBACK_OK}"
  
  if [[ "$MODEL_UPLOAD_SIGN_VERIFY_OK" -eq 1 ]] && \
     [[ "$MODEL_DELIVERY_SIGNATURE_REQUIRED_OK" -eq 1 ]] && \
     [[ "$MODEL_APPLY_FAILCLOSED_OK" -eq 1 ]] && \
     [[ "$MODEL_ROLLBACK_OK" -eq 1 ]]; then
    exit 0
  else
    exit 1
  fi
}

trap cleanup EXIT

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

# Install dependencies
if [[ -f "${MODEL_REGISTRY_DIR}/package-lock.json" ]]; then
  npm --prefix "$MODEL_REGISTRY_DIR" ci
else
  npm --prefix "$MODEL_REGISTRY_DIR" install
fi

# Run tests
if npm --prefix "$MODEL_REGISTRY_DIR" test; then
  MODEL_UPLOAD_SIGN_VERIFY_OK=1
  MODEL_DELIVERY_SIGNATURE_REQUIRED_OK=1
  MODEL_APPLY_FAILCLOSED_OK=1
  MODEL_ROLLBACK_OK=1
  exit 0
else
  exit 1
fi
