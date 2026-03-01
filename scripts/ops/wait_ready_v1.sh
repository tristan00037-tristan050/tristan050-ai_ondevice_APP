#!/usr/bin/env bash
# CI wait: poll /readyz (path from PROBES_SSOT_V1) until 200 or timeout.
set -euo pipefail
READY_PATH="${READY_PATH:-/readyz}"
# Usage: BASE_URL=https://... ./wait_ready_v1.sh
base="${BASE_URL:-http://localhost:8081}"
until curl -sf "${base}${READY_PATH}" >/dev/null 2>&1; do
  sleep 2
done
