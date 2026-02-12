#!/usr/bin/env bash
set -euo pipefail

OPS_HUB_TRACE_BIND_AUTH_POLICY_V1_OK=0
trap 'echo "OPS_HUB_TRACE_BIND_AUTH_POLICY_V1_OK=$OPS_HUB_TRACE_BIND_AUTH_POLICY_V1_OK"' EXIT

doc="docs/ops/contracts/TRACE_BIND_AUTH_POLICY_V1.md"
[ -f "$doc" ] || { echo "BLOCK: missing $doc"; exit 1; }
grep -q "TRACE_BIND_AUTH_POLICY_V1_TOKEN=1" "$doc" || { echo "BLOCK: missing policy token"; exit 1; }

# 코드 토큰이 존재하는지 "범위 제한" 스캔 (문서 제외, node_modules 제외)
# rg 금지: grep + find로만
find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.mjs' -o -name '*.cjs' \) \
  -not -path './docs/*' -not -path '*/node_modules/*' -print0 \
| xargs -0 grep -n "TRACE_BIND_MODE=LOCAL_ONLY_V1" >/dev/null || { echo "BLOCK: missing TRACE_BIND_MODE token in code"; exit 1; }

find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.mjs' -o -name '*.cjs' \) \
  -not -path './docs/*' -not -path '*/node_modules/*' -print0 \
| xargs -0 grep -n "TRACE_AUTH_MODE=API_KEY_REQUIRED_V1" >/dev/null || { echo "BLOCK: missing TRACE_AUTH_MODE token in code"; exit 1; }

find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.mjs' -o -name '*.cjs' \) \
  -not -path './docs/*' -not -path '*/node_modules/*' -print0 \
| xargs -0 grep -n "TRACE_API_KEY_EXPECTED_TOKEN=1" >/dev/null || { echo "BLOCK: missing TRACE_API_KEY_EXPECTED_TOKEN token in code"; exit 1; }

# 금지 바인딩 문자열이 trace 관련 파일에 들어가면 BLOCK(범위 제한: trace/ops/hub 경로만)
# -print0 / xargs -0 사용 (공백/한글 경로 안전)
TMPDIR="${TMPDIR:-/tmp}"
TRACE_FILES_TMP="$(mktemp)"
trap "rm -f '$TRACE_FILES_TMP'" EXIT

find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.mjs' -o -name '*.cjs' \) \
  -not -path './docs/*' -not -path '*/node_modules/*' -print0 \
| xargs -0 grep -lE 'trace|ops|hub' 2>/dev/null > "$TRACE_FILES_TMP" || true

FOUND_FORBIDDEN=0
if [ -s "$TRACE_FILES_TMP" ]; then
  while IFS= read -r f; do
    if grep -n "0.0.0.0" "$f" >/dev/null 2>&1; then
      echo "BLOCK: 0.0.0.0 bind detected in $f"
      FOUND_FORBIDDEN=1
    fi
    if grep -nE "\b::\b" "$f" >/dev/null 2>&1; then
      echo "BLOCK: :: bind detected in $f"
      FOUND_FORBIDDEN=1
    fi
  done < "$TRACE_FILES_TMP"
fi

[ "$FOUND_FORBIDDEN" -eq 0 ] || exit 1

OPS_HUB_TRACE_BIND_AUTH_POLICY_V1_OK=1
exit 0
