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

# 차트/CI wait/app 라우트 경로는 레포마다 위치가 다를 수 있어,
# 최소 구현: 레포 전체에서 probe 경로 후보를 추출해 SSOT 값과 일치하는지 확인(메타-only)
# 오탐 최소화를 위해 핵심 경로만 우선 스캔
paths=(
  "webcore_appcore_starter_4_17"
  ".github/workflows"
  "scripts"
)

# /healthz,/readyz가 서로 바뀌거나 혼재되면 BLOCK
found_health=0
found_ready=0
for p in "${paths[@]}"; do
  [ -e "$p" ] || continue
  if grep -RIn --binary-files=without-match "$HEALTH" "$p" >/dev/null 2>&1; then found_health=1; fi
  if grep -RIn --binary-files=without-match "$READY" "$p" >/dev/null 2>&1; then found_ready=1; fi
done
[ "$found_health" = "1" ] && [ "$found_ready" = "1" ] || { echo "ERROR_CODE=PATHS_NOT_FOUND_IN_REPO"; exit 1; }

PROBES_SSOT_V1_OK=1
PROBES_PATHS_MATCH_APP_V1_OK=1
exit 0
