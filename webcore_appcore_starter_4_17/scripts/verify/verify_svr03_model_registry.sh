#!/usr/bin/env bash
set -euo pipefail

TOPLEVEL="$(git rev-parse --show-toplevel)"
ROOT="${TOPLEVEL}/webcore_appcore_starter_4_17"

MODEL_UPLOAD_SIGN_VERIFY_OK=0
MODEL_DELIVERY_SIGNATURE_REQUIRED_OK=0
MODEL_APPLY_FAILCLOSED_OK=0
MODEL_ROLLBACK_OK=0

cleanup() {
  echo "MODEL_UPLOAD_SIGN_VERIFY_OK=${MODEL_UPLOAD_SIGN_VERIFY_OK}"
  echo "MODEL_DELIVERY_SIGNATURE_REQUIRED_OK=${MODEL_DELIVERY_SIGNATURE_REQUIRED_OK}"
  echo "MODEL_APPLY_FAILCLOSED_OK=${MODEL_APPLY_FAILCLOSED_OK}"
  echo "MODEL_ROLLBACK_OK=${MODEL_ROLLBACK_OK}"
}
trap cleanup EXIT

# Guard: evidence contamination (tests must not print OK=1)
if command -v rg >/dev/null 2>&1; then
  if rg -n "OK=1" "${ROOT}/backend/model_registry/tests"; then
    exit 1
  fi
fi

cd "${ROOT}/backend/model_registry"

if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi

npm test

MODEL_UPLOAD_SIGN_VERIFY_OK=1
MODEL_DELIVERY_SIGNATURE_REQUIRED_OK=1
MODEL_APPLY_FAILCLOSED_OK=1
MODEL_ROLLBACK_OK=1
exit 0
