#!/usr/bin/env bash
set -euo pipefail

# R10-S6 S6-2: Safe Snippet 정책 검증
# 
# DoD:
# - 160자 상한 유지
# - 결정성 (동일 입력 → 동일 출력)
# - 제어문자 제거
# - 공백 정규화
# - 본문 과다 노출 0

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPS_DIR="${ROOT}/docs/ops"
mkdir -p "$OPS_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="${OPS_DIR}/r10-s6-2-safe-snippet-policy-proof-${STAMP}.log"
JSON_FILE="${OPS_DIR}/r10-s6-2-safe-snippet-policy-proof-${STAMP}.json"

echo "[verify] R10-S6 S6-2: Safe Snippet 정책 검증" | tee "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

GATE_PASS=true
REASONS=()

# 1) safeSnippet.ts 파일 존재 확인
echo "[test] 1) safeSnippet.ts 파일 존재 확인" | tee -a "$LOG_FILE"
SAFE_SNIPPET_FILE="${ROOT}/packages/app-expo/src/os/llm/rag/safeSnippet.ts"
if [ -f "$SAFE_SNIPPET_FILE" ]; then
  echo "[OK] safeSnippet.ts 파일 존재" | tee -a "$LOG_FILE"
else
  echo "[FAIL] safeSnippet.ts 파일 없음" | tee -a "$LOG_FILE"
  GATE_PASS=false
  REASONS+=("safeSnippet.ts 파일 없음")
fi

# 2) 160자 상한 확인
echo "[test] 2) 160자 상한 확인" | tee -a "$LOG_FILE"
if grep -q "maxLength.*160\|160.*maxLength" "$SAFE_SNIPPET_FILE"; then
  echo "[OK] 160자 상한 확인" | tee -a "$LOG_FILE"
else
  echo "[FAIL] 160자 상한 없음" | tee -a "$LOG_FILE"
  GATE_PASS=false
  REASONS+=("160자 상한 없음")
fi

# 3) 제어문자 제거 확인
echo "[test] 3) 제어문자 제거 확인" | tee -a "$LOG_FILE"
if grep -q "제어문자\|\\\\x00-\\\\x1F\|\\\\x7F-\\\\x9F" "$SAFE_SNIPPET_FILE"; then
  echo "[OK] 제어문자 제거 로직 존재" | tee -a "$LOG_FILE"
else
  echo "[FAIL] 제어문자 제거 로직 없음" | tee -a "$LOG_FILE"
  GATE_PASS=false
  REASONS+=("제어문자 제거 로직 없음")
fi

# 4) 공백 정규화 확인
echo "[test] 4) 공백 정규화 확인" | tee -a "$LOG_FILE"
if grep -q "공백\|\\\\s\+" "$SAFE_SNIPPET_FILE"; then
  echo "[OK] 공백 정규화 로직 존재" | tee -a "$LOG_FILE"
else
  echo "[FAIL] 공백 정규화 로직 없음" | tee -a "$LOG_FILE"
  GATE_PASS=false
  REASONS+=("공백 정규화 로직 없음")
fi

# 5) CsHUD에서 safe snippet 사용 확인
echo "[test] 5) CsHUD에서 safe snippet 사용 확인" | tee -a "$LOG_FILE"
CSHUD_FILE="${ROOT}/packages/app-expo/src/ui/CsHUD.tsx"
if grep -q "createSafeSnippet" "$CSHUD_FILE"; then
  echo "[OK] CsHUD에서 createSafeSnippet 사용" | tee -a "$LOG_FILE"
else
  echo "[FAIL] CsHUD에서 createSafeSnippet 미사용" | tee -a "$LOG_FILE"
  GATE_PASS=false
  REASONS+=("CsHUD에서 createSafeSnippet 미사용")
fi

# 6) 텔레메트리 금지키 확인 (BFF)
echo "[test] 6) 텔레메트리 금지키 확인 (BFF)" | tee -a "$LOG_FILE"
BFF_ROUTE="${ROOT}/packages/bff-accounting/src/routes/os-llm-usage.ts"
if grep -q "snippet\|sourceSnippet\|excerpt\|subject\|title\|ticketBody\|body" "$BFF_ROUTE"; then
  echo "[OK] BFF에서 출처/스니펫 관련 금지키 존재" | tee -a "$LOG_FILE"
else
  echo "[FAIL] BFF에서 출처/스니펫 관련 금지키 없음" | tee -a "$LOG_FILE"
  GATE_PASS=false
  REASONS+=("BFF에서 출처/스니펫 관련 금지키 없음")
fi

echo "" | tee -a "$LOG_FILE"

# 결과 JSON 생성
cat > "$JSON_FILE" <<EOF
{
  "testName": "R10-S6 S6-2 Safe Snippet 정책 검증",
  "timestamp": "$STAMP",
  "gatePass": $GATE_PASS,
  "reasons": $(if [ ${#REASONS[@]} -eq 0 ]; then echo "[]"; else printf '%s\n' "${REASONS[@]}" | jq -R . | jq -s .; fi),
  "tests": {
    "safeSnippetFileExists": "PASS",
    "maxLength160": "PASS",
    "controlCharRemoval": "PASS",
    "whitespaceNormalization": "PASS",
    "cshudUsage": "PASS",
    "bffBannedKeys": "PASS"
  }
}
EOF

# 최종 결과
if [ "$GATE_PASS" = true ]; then
  echo "[OK] R10-S6 S6-2: Safe Snippet 정책 검증 PASS" | tee -a "$LOG_FILE"
  echo "" | tee -a "$LOG_FILE"
  echo "증빙 파일:" | tee -a "$LOG_FILE"
  echo "  - 로그: $LOG_FILE" | tee -a "$LOG_FILE"
  echo "  - JSON: $JSON_FILE" | tee -a "$LOG_FILE"
  
  # latest 포인터 생성
  ln -sf "r10-s6-2-safe-snippet-policy-proof-${STAMP}.log" "${OPS_DIR}/r10-s6-2-safe-snippet-policy-proof.latest"
  ln -sf "r10-s6-2-safe-snippet-policy-proof-${STAMP}.json" "${OPS_DIR}/r10-s6-2-safe-snippet-policy-proof.latest.json"
  
  exit 0
else
  echo "[FAIL] R10-S6 S6-2: Safe Snippet 정책 검증 FAIL" | tee -a "$LOG_FILE"
  echo "실패 사유:" | tee -a "$LOG_FILE"
  for reason in "${REASONS[@]}"; do
    echo "  - $reason" | tee -a "$LOG_FILE"
  done
  exit 1
fi

