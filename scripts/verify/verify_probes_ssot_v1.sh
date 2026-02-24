#!/usr/bin/env bash
# PR-P0-DEPLOY-01: Chart/app/CI probe paths single SSOT (/healthz, /readyz). Fail-closed on drift.
# Output: key=value only (no sensitive data).
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_ROOT"

PROBES_SSOT_V1_OK=0
PROBES_PATHS_MATCH_APP_V1_OK=0
probes_ssot_health_path="/healthz"
probes_ssot_ready_path="/readyz"
probe_chart_readiness_path=""
probe_chart_liveness_path=""
probe_ci_wait_path=""
probe_app_health_path=""
probe_app_ready_path=""
probes_ssot_fail_class="unknown"
probes_ssot_fail_hint=""

cleanup() {
  echo "PROBES_SSOT_V1_OK=${PROBES_SSOT_V1_OK}"
  echo "PROBES_PATHS_MATCH_APP_V1_OK=${PROBES_PATHS_MATCH_APP_V1_OK}"
  echo "probes_ssot_health_path=${probes_ssot_health_path}"
  echo "probes_ssot_ready_path=${probes_ssot_ready_path}"
  echo "probe_chart_readiness_path=${probe_chart_readiness_path}"
  echo "probe_chart_liveness_path=${probe_chart_liveness_path}"
  echo "probe_ci_wait_path=${probe_ci_wait_path}"
  echo "probe_app_health_path=${probe_app_health_path}"
  echo "probe_app_ready_path=${probe_app_ready_path}"
  if [[ "$PROBES_SSOT_V1_OK" != "1" ]]; then
    echo "probes_ssot_fail_class=${probes_ssot_fail_class}"
    echo "probes_ssot_fail_hint=${probes_ssot_fail_hint}"
  fi
}
trap cleanup EXIT

CHART_DEPLOY="webcore_appcore_starter_4_17/charts/bff-accounting/templates/deployment.yaml"
APP_INDEX="webcore_appcore_starter_4_17/packages/bff-accounting/src/index.ts"
CI_WORKFLOW=".github/workflows/release.yml"

if [[ ! -f "$CHART_DEPLOY" ]]; then
  probes_ssot_fail_class="app_missing_route"
  probes_ssot_fail_hint="chart deployment not found: ${CHART_DEPLOY}"
  exit 1
fi
if [[ ! -f "$APP_INDEX" ]]; then
  probes_ssot_fail_class="app_missing_route"
  probes_ssot_fail_hint="app index not found: ${APP_INDEX}"
  exit 1
fi
if [[ ! -f "$CI_WORKFLOW" ]]; then
  probes_ssot_fail_class="ci_wait_drift"
  probes_ssot_fail_hint="workflow not found: ${CI_WORKFLOW}"
  exit 1
fi

# Chart: require path: /readyz and path: /healthz (exact SSOT)
probe_chart_readiness_path="$(grep -E "path:[[:space:]]*/[^ ,}]+" "$CHART_DEPLOY" | head -1 | sed -n 's/.*path:[[:space:]]*\([^ ,}]*\).*/\1/p')"
probe_chart_liveness_path="$(grep -E "path:[[:space:]]*/[^ ,}]+" "$CHART_DEPLOY" | tail -1 | sed -n 's/.*path:[[:space:]]*\([^ ,}]*\).*/\1/p')"
# Order in file: readiness then liveness, so first path=readiness, second=liveness
if [[ -z "$probe_chart_readiness_path" ]] || [[ -z "$probe_chart_liveness_path" ]]; then
  probes_ssot_fail_class="chart_drift"
  probes_ssot_fail_hint="chart probe path missing (readiness=${probe_chart_readiness_path:-empty}, liveness=${probe_chart_liveness_path:-empty})"
  exit 1
fi
if [[ "$probe_chart_readiness_path" != "${probes_ssot_ready_path}" ]] || [[ "$probe_chart_liveness_path" != "${probes_ssot_health_path}" ]]; then
  probes_ssot_fail_class="chart_drift"
  probes_ssot_fail_hint="chart must use ${probes_ssot_health_path} and ${probes_ssot_ready_path}; got liveness=${probe_chart_liveness_path} readiness=${probe_chart_readiness_path}"
  exit 1
fi

# App: must define /healthz and /readyz
if ! grep -q '"/healthz"' "$APP_INDEX" && ! grep -q "'/healthz'" "$APP_INDEX"; then
  probes_ssot_fail_class="app_missing_route"
  probes_ssot_fail_hint="app must define GET /healthz in ${APP_INDEX}"
  exit 1
fi
if ! grep -q '"/readyz"' "$APP_INDEX" && ! grep -q "'/readyz'" "$APP_INDEX"; then
  probes_ssot_fail_class="app_missing_route"
  probes_ssot_fail_hint="app must define GET /readyz in ${APP_INDEX}"
  exit 1
fi
probe_app_health_path="${probes_ssot_health_path}"
probe_app_ready_path="${probes_ssot_ready_path}"
PROBES_PATHS_MATCH_APP_V1_OK=1

# CI: ready wait and any curl to 8081 must use only /healthz or /readyz
ci_paths="$(grep -E "8081/(healthz|readyz|health|ready)[^0-9a-zA-Z_]?" "$CI_WORKFLOW" 2>/dev/null || true)"
if echo "$ci_paths" | grep -qE "8081/health[^z]|8081/ready[^z]"; then
  probes_ssot_fail_class="ci_wait_drift"
  probes_ssot_fail_hint="CI must use only /healthz and /readyz in ${CI_WORKFLOW}; found non-SSOT path"
  exit 1
fi
# Prefer the path used in the wait loop (readyz)
if grep -q "8081/readyz" "$CI_WORKFLOW"; then
  probe_ci_wait_path="/readyz"
else
  probes_ssot_fail_class="ci_wait_drift"
  probes_ssot_fail_hint="CI ready wait must call /readyz in ${CI_WORKFLOW}"
  exit 1
fi

PROBES_SSOT_V1_OK=1
exit 0
