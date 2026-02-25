#!/usr/bin/env bash
# P0-01: Meta-only verifier for dockerless repo guard report contract.
# Assumes report was just generated under DOCKER_HOST=unix:///... (docker inaccessible).
# Output: KEY=VALUE only. Exit 0 when all 3 DoD keys pass.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
REPORT_JSON="${REPORT_JSON:-$REPO_ROOT/docs/ops/reports/repo_contracts_latest.json}"

DOCKERLESS_REPORT_RUN_OK=0
DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=0
DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=0

if [[ ! -f "$REPORT_JSON" ]] || [[ ! -s "$REPORT_JSON" ]]; then
  echo "DOCKERLESS_REPORT_RUN_OK=0"
  echo "DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=0"
  echo "DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=0"
  exit 1
fi

# 1) Report was created
DOCKERLESS_REPORT_RUN_OK=1

# 2) Docker key must exist and be "0" (degrade, not missing)
docker_val=
if command -v node >/dev/null 2>&1; then
  docker_val=$(node -e "const r=require(process.argv[1]); process.stdout.write(String(r?.keys?.DOCKER_IT_NET_DB_SVCNAME_V1_OK ?? ''));" "$REPORT_JSON" 2>/dev/null || true)
fi
if [[ "$docker_val" = "0" ]]; then
  DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=1
fi

# 3) Host static policy key must exist (violation would have failed earlier)
host_val=
if command -v node >/dev/null 2>&1; then
  host_val=$(node -e "const r=require(process.argv[1]); const v=r?.keys?.HOST_DOCKER_INTERNAL_FORBIDDEN_OK; process.stdout.write(v !== undefined ? String(v) : '');" "$REPORT_JSON" 2>/dev/null || true)
fi
if [[ -n "$host_val" ]]; then
  DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=1
fi

echo "DOCKERLESS_REPORT_RUN_OK=$DOCKERLESS_REPORT_RUN_OK"
echo "DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK=$DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK"
echo "DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK=$DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK"

if [[ "$DOCKERLESS_REPORT_RUN_OK" != "1" ]] || [[ "$DOCKERLESS_REPORT_DEGRADED_DOCKER_KEYS_OK" != "1" ]] || [[ "$DOCKERLESS_REPORT_STATIC_POLICY_ALWAYS_ON_OK" != "1" ]]; then
  exit 1
fi
exit 0
