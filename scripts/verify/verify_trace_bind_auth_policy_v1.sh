#!/usr/bin/env bash
set -euo pipefail

OPS_HUB_TRACE_BIND_AUTH_POLICY_V1_OK=0
trap 'echo "OPS_HUB_TRACE_BIND_AUTH_POLICY_V1_OK=$OPS_HUB_TRACE_BIND_AUTH_POLICY_V1_OK"' EXIT

doc="docs/ops/contracts/TRACE_BIND_AUTH_POLICY_V1.md"
[ -f "$doc" ] || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "TRACE_BIND_AUTH_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

# 코드 토큰이 존재하는지 "범위 제한" 스캔 (문서 제외)
# rg 금지: grep + find로만
CODE_HITS_BIND="$(find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.mjs' -o -name '*.cjs' \) \
  -not -path './docs/*' -print0 | xargs -0 grep -n "TRACE_BIND_MODE=LOCAL_ONLY_V1" || true)"
CODE_HITS_AUTH="$(find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.mjs' -o -name '*.cjs' \) \
  -not -path './docs/*' -print0 | xargs -0 grep -n "TRACE_AUTH_MODE=API_KEY_REQUIRED_V1" || true)"
CODE_HITS_KEYT="$(find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.mjs' -o -name '*.cjs' \) \
  -not -path './docs/*' -print0 | xargs -0 grep -n "TRACE_API_KEY_EXPECTED_TOKEN=1" || true)"

[ -n "$CODE_HITS_BIND" ] || { echo "BLOCK: missing TRACE_BIND_MODE token in code"; exit 1; }
[ -n "$CODE_HITS_AUTH" ] || { echo "BLOCK: missing TRACE_AUTH_MODE token in code"; exit 1; }
[ -n "$CODE_HITS_KEYT" ] || { echo "BLOCK: missing TRACE_API_KEY_EXPECTED_TOKEN token in code"; exit 1; }

# 금지 바인딩 문자열이 trace 관련 파일에 들어가면 BLOCK(범위 제한: trace/ops/hub 경로만)
TRACE_FILES="$(find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.mjs' -o -name '*.cjs' \) \
  -not -path './docs/*' | grep -E 'trace|ops|hub' || true)"

if [ -n "$TRACE_FILES" ]; then
  echo "$TRACE_FILES" | xargs grep -n "0.0.0.0" && { echo "BLOCK: 0.0.0.0 bind detected"; exit 1; } || true
  echo "$TRACE_FILES" | xargs grep -nE "\b::\b" && { echo "BLOCK: :: bind detected"; exit 1; } || true
fi

OPS_HUB_TRACE_BIND_AUTH_POLICY_V1_OK=1
exit 0

