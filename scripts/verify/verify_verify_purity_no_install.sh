#!/usr/bin/env bash
set -euo pipefail

VERIFY_PURITY_NO_INSTALL_OK=0
cleanup(){ echo "VERIFY_PURITY_NO_INSTALL_OK=${VERIFY_PURITY_NO_INSTALL_OK}"; }
trap cleanup EXIT

# 이번 PR 범위: E2E verify + perf real-pipeline verify만 순수성 검사
TARGETS=(
  "scripts/verify/verify_perf_real_pipeline_p95.sh"
  "webcore_appcore_starter_4_17/scripts/verify/verify_web_ux_01_mode_switch_e2e.sh"
  "webcore_appcore_starter_4_17/scripts/verify/verify_web_ux_03_export_auditv2_e2e.sh"
  "webcore_appcore_starter_4_17/scripts/verify/verify_web_ux_04_p95_marks_parity_e2e.sh"
  "webcore_appcore_starter_4_17/scripts/verify/verify_web_ux_08_meta_only_negative_suite.sh"
)

BAD_REGEX='(npm (ci|install)|pnpm (i|install)|yarn (install|add)|playwright install|apt-get|apk add|brew install|curl https?://|wget https?://)'

HIT="$(grep -RInE "$BAD_REGEX" "${TARGETS[@]}" 2>/dev/null || true)"

# 주석/echo에 들어간 문자열은 제외(실행 커맨드만 차단)
HIT="$(echo "$HIT" | grep -v '^[^:]*:[0-9]*:#' | grep -v 'echo' || true)"

if [[ -n "$HIT" ]]; then
  echo "BLOCK: install/network command found in verify scripts (scope: e2e+perf)"
  echo "$HIT"
  exit 1
fi

VERIFY_PURITY_NO_INSTALL_OK=1
exit 0
