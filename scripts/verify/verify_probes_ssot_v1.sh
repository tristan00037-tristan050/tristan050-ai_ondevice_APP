#!/usr/bin/env bash
set -euo pipefail

PROBES_SSOT_V1_OK=0
PROBES_PATHS_MATCH_APP_V1_OK=0

finish() {
  echo "PROBES_SSOT_V1_OK=${PROBES_SSOT_V1_OK}"
  echo "PROBES_PATHS_MATCH_APP_V1_OK=${PROBES_PATHS_MATCH_APP_V1_OK}"
}
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SSOT="docs/ops/contracts/PROBES_SSOT_V1.md"
test -f "$SSOT" || { echo "ERROR_CODE=SSOT_MISSING"; exit 1; }
grep -q '^PROBES_SSOT_V1_TOKEN=1' "$SSOT" || { echo "ERROR_CODE=SSOT_TOKEN_MISSING"; exit 1; }

HEALTH="$(grep -E '^HEALTH_PATH=' "$SSOT" | tail -n1 | cut -d= -f2 | tr -d '\r')"
READY="$(grep -E '^READY_PATH=' "$SSOT" | tail -n1 | cut -d= -f2 | tr -d '\r')"
[ -n "$HEALTH" ] && [ -n "$READY" ] || { echo "ERROR_CODE=SSOT_VALUES_MISSING"; exit 1; }

# ---- Surface 1: Helm chart probes must match SSOT ----
# 후보 경로(레포 구조 고정, 존재하는 첫 파일 사용)
chart_candidates=(
  "webcore_appcore_starter_4_17/charts/bff-accounting/templates/deployment.yaml"
  "webcore_appcore_starter_4_17/charts/bff-accounting/templates/deployment.yml"
  "webcore_appcore_starter_4_17/charts/bff/templates/deployment.yaml"
  "webcore_appcore_starter_4_17/charts/bff/templates/deployment.yml"
)

chart_file=""
for c in "${chart_candidates[@]}"; do
  if [ -f "$c" ]; then chart_file="$c"; break; fi
done
[ -n "$chart_file" ] || { echo "ERROR_CODE=CHART_DEPLOYMENT_NOT_FOUND"; exit 1; }

# readinessProbe/livenessProbe must use READY/HEALTH paths (path may appear on following lines)
if ! grep -qF "path: ${READY}" "$chart_file"; then
  echo "ERROR_CODE=CHART_READINESS_PATH_MISMATCH"
  exit 1
fi
if ! grep -qF "path: ${HEALTH}" "$chart_file"; then
  echo "ERROR_CODE=CHART_LIVENESS_PATH_MISMATCH"
  exit 1
fi

# ---- Surface 2: CI wait script must match SSOT ----
# 후보 경로(존재하는 첫 파일 사용)
ci_wait_candidates=(
  "scripts/ops/wait_ready_v1.sh"
  "scripts/ops/wait_ready.sh"
  "scripts/verify/wait_ready_v1.sh"
)
ci_wait_file=""
for c in "${ci_wait_candidates[@]}"; do
  if [ -f "$c" ]; then ci_wait_file="$c"; break; fi
done
[ -n "$ci_wait_file" ] || { echo "ERROR_CODE=CI_WAIT_SCRIPT_NOT_FOUND"; exit 1; }

# CI wait에서 READY 경로를 사용해야 함
if ! grep -qF "$READY" "$ci_wait_file"; then
  echo "ERROR_CODE=CI_WAIT_READY_PATH_MISMATCH"
  exit 1
fi

# ---- Surface 3: App routes must expose both endpoints ----
# 앱 라우트 파일 후보(존재하는 첫 파일 사용)
app_route_candidates=(
  "webcore_appcore_starter_4_17/packages/bff-accounting/src/routes/health.ts"
  "webcore_appcore_starter_4_17/packages/bff-accounting/src/routes/health.js"
  "webcore_appcore_starter_4_17/packages/bff-accounting/src/routes/probes.ts"
  "webcore_appcore_starter_4_17/packages/bff-accounting/src/routes/probes.js"
)
app_file=""
for c in "${app_route_candidates[@]}"; do
  if [ -f "$c" ]; then app_file="$c"; break; fi
done
[ -n "$app_file" ] || { echo "ERROR_CODE=APP_PROBES_ROUTE_NOT_FOUND"; exit 1; }

# 앱 라우트 파일에서 HEALTH/READY 경로가 모두 존재해야 함
if ! grep -qF "$HEALTH" "$app_file"; then
  echo "ERROR_CODE=APP_HEALTH_PATH_MISSING"
  exit 1
fi
if ! grep -qF "$READY" "$app_file"; then
  echo "ERROR_CODE=APP_READY_PATH_MISSING"
  exit 1
fi

PROBES_SSOT_V1_OK=1
PROBES_PATHS_MATCH_APP_V1_OK=1
exit 0
