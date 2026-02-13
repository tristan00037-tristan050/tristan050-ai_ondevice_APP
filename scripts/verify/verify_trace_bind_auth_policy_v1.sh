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

# 금지 바인딩 문자열이 trace 관련 "경로"에 들어가면 BLOCK (경로 기준, 내용 기준 금지)
# -print0 / xargs -0 사용 (공백/한글 경로 안전)
TMPDIR="${TMPDIR:-/tmp}"
TRACE_FILES_TMP="$(mktemp)"
trap "rm -f '$TRACE_FILES_TMP'" EXIT

# 1) trace/ops/hub "경로" 기준으로 파일 목록 생성 (node_modules 제외)
find . -type f \( -name '*.js' -o -name '*.ts' -o -name '*.mjs' -o -name '*.cjs' \) \
  -not -path './docs/*' -not -path '*/node_modules/*' -print0 \
| tr '\0' '\n' \
| grep -E '/(trace|ops|hub)/' > "$TRACE_FILES_TMP" || true

FOUND_FORBIDDEN=0

# 2) 금지 바인딩은 "문자열 존재"가 아니라 "바인딩 설정 패턴"만 차단 (오탐 방지)
# 허용: 비교/정규화 코드에서 "0.0.0.0" 문자열 언급
# 차단: listen/host/bind에 0.0.0.0 또는 :: 를 직접 넣는 경우
BAD_BIND_RE_1='(listen|bind)\s*\([^)]*["'"'"']0\.0\.0\.0["'"'"']'
BAD_BIND_RE_2='(listen|bind)\s*\([^)]*["'"'"']::["'"'"']'
BAD_BIND_RE_3='(host|hostname)\s*:\s*["'"'"']0\.0\.0\.0["'"'"']'
BAD_BIND_RE_4='(host|hostname)\s*:\s*["'"'"']::["'"'"']'

if [ -s "$TRACE_FILES_TMP" ]; then
  while IFS= read -r f; do
    if grep -nE "$BAD_BIND_RE_1|$BAD_BIND_RE_3" "$f" >/dev/null 2>&1; then
      echo "BLOCK: forbidden bind (0.0.0.0) detected in $f"
      FOUND_FORBIDDEN=1
    fi
    if grep -nE "$BAD_BIND_RE_2|$BAD_BIND_RE_4" "$f" >/dev/null 2>&1; then
      echo "BLOCK: forbidden bind (::) detected in $f"
      FOUND_FORBIDDEN=1
    fi
  done < "$TRACE_FILES_TMP"
fi

[ "$FOUND_FORBIDDEN" -eq 0 ] || exit 1

OPS_HUB_TRACE_BIND_AUTH_POLICY_V1_OK=1
exit 0
