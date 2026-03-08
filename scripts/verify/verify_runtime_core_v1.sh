#!/usr/bin/env bash
set -euo pipefail

VERIFY_RUNTIME_CORE_V1_OK=0
trap 'echo "VERIFY_RUNTIME_CORE_V1_OK=${VERIFY_RUNTIME_CORE_V1_OK}"' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/VERIFY_RUNTIME_CORE_V1.txt"
[[ -f "$SSOT" ]] || { echo "ERROR_CODE=VERIFY_RUNTIME_CORE_SSOT_MISSING"; exit 1; }
grep -q '^VERIFY_RUNTIME_CORE_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=VERIFY_RUNTIME_CORE_TOKEN_MISSING"; exit 1; }

for i in 1 2 3 4 5; do
  key="REQUIRED_RUNTIME_${i}"
  rel="$(grep -E "^${key}=" "$SSOT" | head -n1 | sed "s/^${key}=//" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -n "$rel" ]] || { echo "ERROR_CODE=VERIFY_RUNTIME_CORE_DEF_MISSING"; echo "HIT_KEY=$key"; exit 1; }
  full="${ROOT}/${rel}"
  [[ -f "$full" ]] || { echo "ERROR_CODE=VERIFY_RUNTIME_CORE_FILE_MISSING"; echo "HIT_PATH=$rel"; exit 1; }
  node -e "require(process.argv[1])" "$full" >/dev/null 2>&1 || {
    echo "ERROR_CODE=VERIFY_RUNTIME_CORE_LOAD_FAILED"
    echo "HIT_PATH=$rel"
    exit 1
  }
done

VERIFY_RUNTIME_CORE_V1_OK=1
exit 0
