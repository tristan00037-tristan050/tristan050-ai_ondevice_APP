#!/usr/bin/env bash
set -euo pipefail

# AI-P3-SAFETY: NO_RAW_OUTPUT_POLICY_V1 verifier
NO_RAW_IN_LOGS_OK=0
NO_RAW_IN_EXCEPTIONS_OK=0
NO_RAW_IN_REPORTS_OK=0
trap '
  echo "NO_RAW_IN_LOGS_OK=${NO_RAW_IN_LOGS_OK}"
  echo "NO_RAW_IN_EXCEPTIONS_OK=${NO_RAW_IN_EXCEPTIONS_OK}"
  echo "NO_RAW_IN_REPORTS_OK=${NO_RAW_IN_REPORTS_OK}"
' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "=== NO_RAW_OUTPUT_POLICY_V1 ==="

SEARCH_DIRS="tools/ scripts/ packs/ docs/ops/reports/ docs/ops/PROOFS/"

# 실제 존재하는 경로만 검색 대상으로 설정
EXISTING_DIRS=""
for d in $SEARCH_DIRS; do
  if [ -d "$d" ]; then
    EXISTING_DIRS="$EXISTING_DIRS $d"
  fi
done

if [ -z "$EXISTING_DIRS" ]; then
  echo "WARN: no target directories found, skipping"
  NO_RAW_IN_LOGS_OK=1
  NO_RAW_IN_EXCEPTIONS_OK=1
  NO_RAW_IN_REPORTS_OK=1
  exit 0
fi

# 1. logger/console에 prompt/output 원문 직접 출력 금지
# shellcheck disable=SC2086
HITS_LOGS="$(grep -rn \
  --include="*.ts" --include="*.js" --include="*.sh" \
  -E "(logger|console)\.(info|warn|error|debug)\s*\(.*\\\$\{.*(prompt|raw_output|raw_input)\b" \
  $EXISTING_DIRS 2>/dev/null | grep -v "\.test\." | grep -v "_digest" || true)"

if [ -n "$HITS_LOGS" ]; then
  echo "FAILED_GUARD=RAW_IN_LOGS_DETECTED"
  echo "$HITS_LOGS"
  exit 1
fi
NO_RAW_IN_LOGS_OK=1

# 2. throw new Error에 prompt/output 원문 직접 포함 금지
# shellcheck disable=SC2086
HITS_EXC="$(grep -rn \
  --include="*.ts" --include="*.js" \
  -E "throw new Error\s*\(.*\\\$\{.*(prompt|raw_output|raw_input)\b" \
  $EXISTING_DIRS 2>/dev/null | grep -v "\.test\." || true)"

if [ -n "$HITS_EXC" ]; then
  echo "FAILED_GUARD=RAW_IN_EXCEPTIONS_DETECTED"
  echo "$HITS_EXC"
  exit 1
fi
NO_RAW_IN_EXCEPTIONS_OK=1

# 3. reports / proofs 디렉토리에 raw 문자열 직접 기재 금지
for report_dir in "docs/ops/reports/" "docs/ops/PROOFS/"; do
  if [ -d "$report_dir" ]; then
    HITS_REPORT="$(grep -rn \
      --include="*.json" --include="*.md" --include="*.txt" \
      -E '"(prompt|output|raw_input|raw_response)"\s*:\s*"[^"]{100,}"' \
      "$report_dir" 2>/dev/null || true)"
    if [ -n "$HITS_REPORT" ]; then
      echo "FAILED_GUARD=RAW_IN_REPORTS_DETECTED"
      echo "$HITS_REPORT"
      exit 1
    fi
  fi
done
NO_RAW_IN_REPORTS_OK=1

# 4. no_raw_output_policy_v1.ts 존재 확인
POLICY_TS="tools/safety/no_raw_output_policy_v1.ts"
if ! [ -f "$POLICY_TS" ]; then
  echo "FAILED_GUARD=NO_RAW_POLICY_FILE_MISSING"
  exit 1
fi

# 5. safeLogDigestOnly 존재 확인
if ! grep -q "safeLogDigestOnly" "$POLICY_TS"; then
  echo "FAILED_GUARD=SAFE_LOG_HELPER_MISSING"
  exit 1
fi

# 6. throwSafeError 존재 확인
if ! grep -q "throwSafeError" "$POLICY_TS"; then
  echo "FAILED_GUARD=SAFE_THROW_HELPER_MISSING"
  exit 1
fi

echo "NO_RAW_IN_LOGS_OK=1"
echo "NO_RAW_IN_EXCEPTIONS_OK=1"
echo "NO_RAW_IN_REPORTS_OK=1"
exit 0
