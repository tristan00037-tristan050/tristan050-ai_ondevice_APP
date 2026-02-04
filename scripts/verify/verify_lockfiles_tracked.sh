#!/usr/bin/env bash
set -euo pipefail

LOCKFILES=(
  "webcore_appcore_starter_4_17/backend/attestation/package-lock.json"
  "webcore_appcore_starter_4_17/backend/control_plane/package-lock.json"
  "webcore_appcore_starter_4_17/backend/telemetry/package-lock.json"
  "webcore_appcore_starter_4_17/backend/model_registry/package-lock.json"
  "webcore_appcore_starter_4_17/packages/ops-console/package-lock.json"
)

missing=0
for f in "${LOCKFILES[@]}"; do
  if git ls-files --error-unmatch "$f" >/dev/null 2>&1; then
    echo "OK: LOCKFILE_TRACKED: $f"
  else
    echo "BLOCK: LOCKFILE_NOT_TRACKED: $f"
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "LOCKFILES_TRACKED_OK=0"
  exit 1
fi

echo "LOCKFILES_TRACKED_OK=1"
