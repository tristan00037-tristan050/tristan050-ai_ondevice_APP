#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

# existing compose + dockerfile must exist
test -f docker-compose.yml || { echo "ONPREM_COMPOSE_ASSETS_OK=0"; exit 1; }
test -f Dockerfile.bff || { echo "ONPREM_COMPOSE_ASSETS_OK=0"; exit 1; }

# quickstart doc + smoke script must exist
test -f docs/ONPREM_COMPOSE_QUICKSTART.md || { echo "ONPREM_COMPOSE_ASSETS_OK=0"; exit 1; }
test -f scripts/ops/verify_onprem_compose_quickstart.sh || { echo "ONPREM_COMPOSE_ASSETS_OK=0"; exit 1; }

echo "ONPREM_COMPOSE_ASSETS_OK=1"

