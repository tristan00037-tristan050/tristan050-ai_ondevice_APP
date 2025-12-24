#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
APP="$ROOT/webcore_appcore_starter_4_17"
cd "$APP"

HOST="${BFF_HOST:-http://127.0.0.1:8081}"
URL="$HOST/v1/os/llm-usage"

HDR_COMMON=(
  -H "Content-Type: application/json"
  -H "X-Tenant: default"
  -H "X-User-Id: hud-user-1"
  -H "X-User-Role: operator"
  -H "X-Api-Key: collector-key:operator"
)

ts="$(date -u +"%Y%m%d-%H%M%S")"
OPS_DIR="$APP/docs/ops"
mkdir -p "$OPS_DIR"
LOG="$OPS_DIR/r10-s5-p1-4-perf-kpi-proof-$ts.log"
JSON="$OPS_DIR/r10-s5-p1-4-perf-kpi-proof-$ts.json"
LATEST="$OPS_DIR/r10-s5-p1-4-perf-kpi-proof.latest"

function http_code() {
  local payload="$1"
  local resp_file="/tmp/p1_4_body.txt"
  local err_file="/tmp/p1_4_curl_err.txt"
  
  # ✅ curl -sS: silent이지만 에러는 표시, -w로 HTTP 코드를 변수에 저장
  local code
  code=$(curl -sS -o "$resp_file" -w "%{http_code}" \
    "${HDR_COMMON[@]}" \
    -X POST "$URL" \
    -d "$payload" 2>"$err_file")
  local curl_exit=$?
  
  # curl 실패 시 에러 로깅 및 CURL_ERROR 반환
  if [ $curl_exit -ne 0 ]; then
    {
      echo "[ERROR] curl failed (exit=$curl_exit)"
      echo "stderr:"
      cat "$err_file" 2>/dev/null || true
      echo "response body:"
      cat "$resp_file" 2>/dev/null || true
    } | tee -a "$LOG"
    echo "CURL_ERROR"
    return
  fi
  
  # 응답 바디 로깅 (디버깅용)
  {
    echo "[HTTP $code] response:"
    cat "$resp_file" 2>/dev/null || echo "(empty)"
    echo ""
  } | tee -a "$LOG" > /dev/null
  
  echo "$code"
}

function expect_code() {
  local name="$1"
  local want="$2"
  local payload="$3"
  local got
  got="$(http_code "$payload")"
  {
    echo "[$name] want=$want got=$got"
    echo "[$name] payload=$payload"
    echo ""
  } | tee -a "$LOG"

  if [ "$got" != "$want" ]; then
    echo "[FAIL] $name (want $want got $got) — see $LOG" | tee -a "$LOG"
    exit 1
  fi
  echo "[OK] $name ($got)" | tee -a "$LOG"
}

echo "[verify] R10-S5 P1-4: 성능 KPI meta-only 검증" | tee "$LOG"
echo "" | tee -a "$LOG"

# 0) healthz
if curl -s "$HOST/health" > /dev/null 2>&1 || curl -s "$HOST/healthz" > /dev/null 2>&1; then
  echo "[OK] BFF 서버 실행 중: $HOST" | tee -a "$LOG"
else
  echo "[WARN] BFF 서버 미실행 (검증 건너뜀): $HOST" | tee -a "$LOG"
  echo "[INFO] BFF 서버 시작: ./scripts/dev_bff.sh" | tee -a "$LOG"
  echo "[SKIP] R10-S5 P1-4: 성능 KPI meta-only 검증 SKIP (BFF 미실행)" | tee -a "$LOG"
  exit 0
fi

echo "" | tee -a "$LOG"

# 1) 정상 KPI -> 204
VALID='{
  "eventType":"suggestion_shown",
  "suggestionLength":100,
  "ragEmbeddingMs":120,
  "ragRetrieveMs":80,
  "ragIndexHydrateMs":30,
  "ragIndexBuildMs":0,
  "ragIndexPersistMs":0,
  "ragRetrieveMsP50":80,
  "ragRetrieveMsP95":80,
  "ragDocCount":20,
  "ragTopK":5,
  "ragIndexWarm":true,
  "success":true,
  "fallback":false,
  "cancelled":false
}'
expect_code "valid_meta_kpi" "204" "$VALID"

# 2) 금지키(원문) -> 400
LEAK='{
  "eventType":"suggestion_shown",
  "suggestionLength":0,
  "prompt":"SHOULD_BLOCK"
}'
expect_code "banned_key_prompt" "400" "$LEAK"

# 3) ms 음수 -> 400
NEG_MS='{
  "eventType":"suggestion_shown",
  "suggestionLength":0,
  "ragRetrieveMs":-1
}'
expect_code "invalid_negative_ms" "400" "$NEG_MS"

# 4) ms 상한 초과 -> 400
HIGH_MS='{
  "eventType":"suggestion_shown",
  "suggestionLength":0,
  "ragRetrieveMs":600001
}'
expect_code "invalid_high_ms" "400" "$HIGH_MS"

# 5) topK 범위 위반 -> 400
BAD_TOPK='{
  "eventType":"suggestion_shown",
  "suggestionLength":0,
  "ragTopK":0
}'
expect_code "invalid_topk" "400" "$BAD_TOPK"

# 6) 타입 위반(문자열) -> 400
TYPE_BAD='{
  "eventType":"suggestion_shown",
  "suggestionLength":0,
  "ragDocCount":"20"
}'
expect_code "invalid_type_docCount" "400" "$TYPE_BAD"

# 7) p50/p95 범위 위반 -> 400
BAD_P95='{
  "eventType":"suggestion_shown",
  "suggestionLength":0,
  "ragRetrieveMsP95":600001
}'
expect_code "invalid_p95_ms" "400" "$BAD_P95"

cat > "$JSON" <<EOF
{
  "ts": "$ts",
  "host": "$HOST",
  "url": "$URL",
  "results": {
    "valid_meta_kpi": 204,
    "banned_key_prompt": 400,
    "invalid_negative_ms": 400,
    "invalid_high_ms": 400,
    "invalid_topk": 400,
    "invalid_type_docCount": 400,
    "invalid_p95_ms": 400
  },
  "proofLog": "$(basename "$LOG")"
}
EOF

echo "$(basename "$LOG")" > "$LATEST"
ln -sf "$(basename "$JSON")" "${LATEST}.json"

echo "" | tee -a "$LOG"
echo "[PASS] P1-4 perf KPI meta-only gate — $JSON" | tee -a "$LOG"

