#!/usr/bin/env bash
set -euo pipefail

BAD_REGEX='(npm (ci|install)|pnpm (i|install)|yarn (install|add)|playwright install|apt-get|apk add|brew install|curl https?://|wget https?://)'

HIT="$(grep -RInE "$BAD_REGEX" scripts/verify webcore_appcore_starter_4_17/scripts/verify || true)"
if [ -n "$HIT" ]; then
  echo "BLOCK: install/network command found in verify scripts"
  echo "$HIT"
  exit 1
fi

echo "VERIFY_PURITY_NO_INSTALL_OK=1"

