#!/usr/bin/env bash
set -euo pipefail

# P5-P0-01: ONPREM_LATEST_PASS_MARKER_V1
# - 판정만 (verify=판정만, build/install/download/network 금지)
# - 실패패턴/민감패턴/긴라인/화이트리스트 검사

ONPREM_LATEST_PASS_MARKER_V1_OK=0
ONPREM_LATEST_NO_FAILURE_TEXT_V1_OK=0
ONPREM_LATEST_SENSITIVE_SCAN_V1_OK=0
ONPREM_LATEST_LONG_LINE_BLOCK_V1_OK=0

trap '
echo "ONPREM_LATEST_PASS_MARKER_V1_OK=${ONPREM_LATEST_PASS_MARKER_V1_OK}";
echo "ONPREM_LATEST_NO_FAILURE_TEXT_V1_OK=${ONPREM_LATEST_NO_FAILURE_TEXT_V1_OK}";
echo "ONPREM_LATEST_SENSITIVE_SCAN_V1_OK=${ONPREM_LATEST_SENSITIVE_SCAN_V1_OK}";
echo "ONPREM_LATEST_LONG_LINE_BLOCK_V1_OK=${ONPREM_LATEST_LONG_LINE_BLOCK_V1_OK}";
' EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

POLICY="docs/ops/contracts/ONPREM_PROOF_LATEST_POLICY_V1.md"
LATEST="docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md"
PATTERNS="docs/ops/contracts/PROOF_SENSITIVE_PATTERNS_V1.txt"

# 1) 정책 문서 존재 확인
[ -f "$POLICY" ] || { echo "BLOCK: missing policy: $POLICY"; exit 1; }
grep -q "ONPREM_PROOF_LATEST_POLICY_V1_TOKEN=1" "$POLICY" || { echo "BLOCK: missing policy token"; exit 1; }

# 2) LATEST 파일 존재 확인
[ -f "$LATEST" ] || { echo "BLOCK: missing LATEST: $LATEST"; exit 1; }
[ -s "$LATEST" ] || { echo "BLOCK: LATEST empty: $LATEST"; exit 1; }

# 3) 민감 패턴 SSOT 존재 확인
[ -f "$PATTERNS" ] || { echo "BLOCK: missing patterns SSOT: $PATTERNS"; exit 1; }
[ -s "$PATTERNS" ] || { echo "BLOCK: patterns SSOT empty: $PATTERNS"; exit 1; }

# 4) PASS 마커 검사 (화이트리스트)
# 허용된 PASS 마커: EXIT=0, ok=true, blocks=3, signature.mode=prod 등
PASS_MARKERS=(
  "EXIT=0"
  "ok=true"
  "blocks=3"
  "signature.mode=prod"
  "egress_default=deny"
  "blocked_attempt_observed=true"
  "external_success=false"
)

PASS_FOUND=0
for marker in "${PASS_MARKERS[@]}"; do
  if grep -qF "$marker" "$LATEST"; then
    PASS_FOUND=1
    break
  fi
done

if [ "$PASS_FOUND" = "0" ]; then
  echo "BLOCK: no PASS marker found in LATEST"
  exit 1
fi

ONPREM_LATEST_PASS_MARKER_V1_OK=1

# 5) 실패 패턴 검사 (금지 패턴)
FAILURE_PATTERNS=(
  "EXIT=1"
  "FAIL:"
  "BLOCK:"
  "error:"
  "Error:"
  "ERROR:"
  "failed"
  "Failed"
  "FAILED"
  "exception"
  "Exception"
  "EXCEPTION"
)

FAILURE_FOUND=0
for pattern in "${FAILURE_PATTERNS[@]}"; do
  if grep -qnF "$pattern" "$LATEST" 2>/dev/null; then
    echo "BLOCK: failure pattern found in LATEST: $pattern"
    grep -nF "$pattern" "$LATEST" | head -n 5
    FAILURE_FOUND=1
  fi
done

if [ "$FAILURE_FOUND" = "1" ]; then
  exit 1
fi

ONPREM_LATEST_NO_FAILURE_TEXT_V1_OK=1

# 6) 민감 패턴 검사 (SSOT 기반)
if grep -nFf "$PATTERNS" "$LATEST" >/dev/null 2>&1; then
  echo "BLOCK: sensitive pattern detected in LATEST"
  grep -nFf "$PATTERNS" "$LATEST" | head -n 10
  exit 1
fi

ONPREM_LATEST_SENSITIVE_SCAN_V1_OK=1

# 7) 긴 라인 검사 (500자 초과 BLOCK)
LONG_LINE_FOUND=0
while IFS= read -r line; do
  if [ ${#line} -gt 500 ]; then
    echo "BLOCK: long line detected (len=${#line})"
    LONG_LINE_FOUND=1
    break
  fi
done < "$LATEST"

if [ "$LONG_LINE_FOUND" = "1" ]; then
  exit 1
fi

ONPREM_LATEST_LONG_LINE_BLOCK_V1_OK=1

exit 0

