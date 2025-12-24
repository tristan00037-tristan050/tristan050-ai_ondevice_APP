#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

source "./scripts/_lib/http_gate.sh"

TS="$(date -u +"%Y%m%d-%H%M%S")"
PROOF_DIR="$ROOT/docs/ops"
mkdir -p "$PROOF_DIR"

LOG="$PROOF_DIR/r10-s6-4-perf-proof-$TS.log"
JSON="$PROOF_DIR/r10-s6-4-perf-proof-$TS.json"
LATEST="$PROOF_DIR/r10-s6-4-perf-proof.latest"

# 로그를 proof로 남김
exec > >(tee "$LOG") 2>&1

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "[info] ts=$TS sha=$GIT_SHA"

# 0) dist 신선도는 dev_bff.sh restart가 강제 (A안 적용 전제)
./scripts/dev_bff.sh restart

# 1) preflight
TMP_BODY="$(mktemp -t perf_reg_body.XXXXXX)"
TMP_HDR="$(mktemp -t perf_reg_hdr.XXXXXX)"
code="$(http_gate_request "GET" "http://127.0.0.1:8081/healthz" "$TMP_BODY" "$TMP_HDR")"
http_gate_expect_code "healthz" "$code" "200" "$TMP_BODY"

# 2) 기존 하드 게이트 먼저 통과해야 회귀 감지 의미가 있음
bash scripts/verify_telemetry_rag_meta_only.sh
bash scripts/verify_perf_kpi_meta_only.sh

# 3) 회귀 감지(계약/방화벽) — 허용/거부 케이스를 결정적으로 실행
URL="http://127.0.0.1:8081/v1/os/llm-usage"
HDRS=(
  -H "X-Tenant: default"
  -H "X-User-Id: hud-user-1"
  -H "X-User-Role: operator"
  -H "X-Api-Key: collector-key:operator"
)

pass=true
tests_json=()

run_case () {
  local name="$1"; shift
  local want="$1"; shift
  local payload="$1"; shift

  local body_file hdr_file got
  body_file="$(mktemp -t perf_case_body.XXXXXX)"
  hdr_file="$(mktemp -t perf_case_hdr.XXXXXX)"

  got="$(http_gate_request "POST" "$URL" "$body_file" "$hdr_file" "$payload" "${HDRS[@]}")" || true
  if ! http_gate_expect_code "$name" "$got" "$want" "$body_file"; then
    pass=false
  fi

  tests_json+=("{\"name\":\"$name\",\"want\":$want,\"got\":$got}")
  rm -f "$body_file" "$hdr_file"
}

# (A) 허용 케이스: 숫자/불리언/enum만 포함 + 상한/범위 내
run_case "perf_kpi_allowed" 204 \
'{
  "eventType":"perf_kpi_probe",
  "suggestionLength":0,
  "backend":"real",
  "success":true,
  "fallback":false,
  "cancelled":false,
  "ragEmbeddingMs":12,
  "ragRetrieveMs":20,
  "ragIndexHydrateMs":30,
  "ragIndexBuildMs":40,
  "ragIndexPersistMs":10,
  "ragRetrieveMsP50":20,
  "ragRetrieveMsP95":60,
  "ragDocCount":20,
  "ragTopK":5,
  "ragIndexWarm":true
}'

# (B) 금지키(원문/텍스트) 유입 차단: 400 기대
run_case "banned_text_key_blocked" 400 \
'{
  "eventType":"perf_kpi_probe",
  "suggestionLength":0,
  "prompt":"SHOULD_BLOCK"
}'

# (C) 타입 위반 차단: 400 기대
run_case "type_violation_blocked" 400 \
'{
  "eventType":"perf_kpi_probe",
  "suggestionLength":0,
  "ragRetrieveMsP95":"60"
}'

# (D) 범위 위반 차단: 400 기대
run_case "range_violation_blocked" 400 \
'{
  "eventType":"perf_kpi_probe",
  "suggestionLength":0,
  "ragRetrieveMsP95":600001
}'

# (E) topK 범위 위반 차단: 400 기대
run_case "topk_violation_blocked" 400 \
'{
  "eventType":"perf_kpi_probe",
  "suggestionLength":0,
  "ragTopK":11
}'

# 결과 JSON proof 생성
tests_joined="$(IFS=,; echo "${tests_json[*]}")"
if [ "$pass" = true ]; then
  echo "[OK] perf KPI regression loop PASS"
else
  echo "[FAIL] perf KPI regression loop FAIL"
fi

cat > "$JSON" <<EOF
{
  "ts":"$TS",
  "gitSha":"$GIT_SHA",
  "pass":$( [ "$pass" = true ] && echo "true" || echo "false" ),
  "tests":[ $tests_joined ]
}
EOF

# .latest 포인터 업데이트(로그/JSON 둘 다 추적)
cat > "$LATEST" <<EOF
json=$(basename "$JSON")
log=$(basename "$LOG")
EOF

rm -f "$TMP_BODY" "$TMP_HDR"

# FAIL이면 exit 1로 강제
if [ "$pass" != true ]; then
  exit 1
fi

