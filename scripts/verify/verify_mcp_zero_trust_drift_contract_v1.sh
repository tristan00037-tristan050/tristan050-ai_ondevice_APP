#!/usr/bin/env bash
set -euo pipefail

MCP_ZERO_TRUST_DRIFT_CONTRACT_OK=0
finish() { echo "MCP_ZERO_TRUST_DRIFT_CONTRACT_OK=${MCP_ZERO_TRUST_DRIFT_CONTRACT_OK}"; }
trap finish EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

WATCHED=(
  "docs/ops/contracts/MCP_CAPABILITIES_SSOT_V1.txt"
  "tools/mcp_gateway/CAPABILITIES_DECLARED_V1.txt"
  "tools/mcp_gateway/enforcer_v1.cjs"
)
REQUIRED_GUARDS=(
  "mcp capabilities ssot v1"
  "mcp zero trust enforced v1"
)
CONTRACTS="scripts/verify/verify_repo_contracts.sh"

# base ref(origin/main)가 없으면 fail-closed (shallow/detached 환경에서 drift 우회 차단)
if ! git rev-parse --verify origin/main >/dev/null 2>&1; then
  echo "ERROR_CODE=BASE_REF_UNAVAILABLE"
  exit 1
fi

diff_names="$(git diff --name-only origin/main...HEAD 2>/dev/null)" || {
  echo "ERROR_CODE=GIT_DIFF_FAILED"
  exit 1
}

changed=0
for f in "${WATCHED[@]}"; do
  if echo "$diff_names" | grep -qF "$f"; then
    changed=1
    break
  fi
done

if [ "$changed" -eq 0 ]; then
  MCP_ZERO_TRUST_DRIFT_CONTRACT_OK=1
  exit 0
fi

for g in "${REQUIRED_GUARDS[@]}"; do
  # 주석(# ...)이나 문자열 잔존을 통과로 인정하지 않음.
  # "실제로 실행되는" run_guard 라인만 인정: (선행 공백 허용) + 라인 시작에 run_guard
  if ! grep -Eq "^[[:space:]]*run_guard[[:space:]]+\"${g}\"[[:space:]]+" "$CONTRACTS" 2>/dev/null; then
    echo "ERROR_CODE=MISSING_REQUIRED_GUARD"
    echo "MISSING_GUARD=${g}"
    exit 1
  fi
done

MCP_ZERO_TRUST_DRIFT_CONTRACT_OK=1
exit 0
