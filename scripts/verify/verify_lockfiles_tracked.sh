#!/usr/bin/env bash
set -euo pipefail

# Check lockfiles that are explicitly allowed in .gitignore
LOCKFILES=(
  "webcore_appcore_starter_4_17/packages/ops-console/package-lock.json"
  "webcore_appcore_starter_4_17/backend/telemetry/package-lock.json"
  "webcore_appcore_starter_4_17/backend/model_registry/package-lock.json"
  "webcore_appcore_starter_4_17/backend/control_plane/package-lock.json"
  "webcore_appcore_starter_4_17/backend/attestation/package-lock.json"
)

missing=0
for f in "${LOCKFILES[@]}"; do
  if [ -f "$f" ]; then
    if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
      echo "OK: LOCKFILE_TRACKED: $f"
    else
      echo "BLOCK: LOCKFILE_NOT_TRACKED: $f"
      missing=1
    fi
  else
    echo "SKIP: LOCKFILE_MISSING: $f (file does not exist)"
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "LOCKFILES_TRACKED_OK=0"
  exit 1
fi

echo "LOCKFILES_TRACKED_OK=1"
