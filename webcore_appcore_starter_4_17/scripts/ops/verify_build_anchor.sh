#!/usr/bin/env bash
set -euo pipefail

# ✅ B) zsh parse error 재발 0: 복잡한 검증은 scripts/ops/*.sh로만 제공
# 역할: build anchor 무결성 검증 (헤더/JSON 분리 + fail-fast)
# 출력 표준: 성공 시 `OK: buildSha matches HEAD(<short>)`
# 실패 시: 원인 1줄 + exit 1 (PASS 요약 금지)

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

# BASE_URL 환경변수 지원 (기본값: http://127.0.0.1:8081)
BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"
HEALTHZ_URL="${BASE_URL%/}/healthz"

TMP_HDR="$(mktemp -t verify_anchor_hdr.XXXXXX)"
TMP_BODY="$(mktemp -t verify_anchor_body.XXXXXX)"

# 1) healthz 200 확인 (fail-safe + 재시도 + 진단)
# ✅ 실패/예외/타임아웃에서도 http_code는 절대 빈 문자열이 되지 않는다(기본값 000)
# ✅ 레이스 방지: 최대 5초(0.2s * 25) 재시도
http_code="000"
for i in $(seq 1 25); do
  http_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "$HEALTHZ_URL" 2>/dev/null || echo 000)"
  [ "$http_code" = "200" ] && break
  sleep 0.2
done

if [ "$http_code" != "200" ]; then
  echo "[FAIL] healthz returned $http_code (expected 200)"
  echo "[diag] LISTEN 8081:"; lsof -nP -iTCP:8081 -sTCP:LISTEN || true
  echo "[diag] curl -v (2s):"; curl -v --max-time 2 "$HEALTHZ_URL" || true
  echo "[diag] tail /tmp/bff_dev.log:"; tail -n 120 /tmp/bff_dev.log 2>/dev/null || true
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

# 2) 헤더 buildSha 추출 (완전 분리, status code 확인 후)
build_sha_header=$(curl -fsSI --max-time 3 "$HEALTHZ_URL" -D "$TMP_HDR" -o /dev/null 2>/dev/null && grep -i "^x-os-build-sha:" "$TMP_HDR" 2>/dev/null | cut -d' ' -f2- | tr -d '\r' | head -1 || echo "")

# 3) JSON buildSha 추출 (완전 분리, status code 확인과 절대 섞지 않음)
healthz_json="$(curl -fsS --max-time 2 "$HEALTHZ_URL")"
build_sha_json=$(echo "$healthz_json" | jq -r '.buildSha // empty' 2>/dev/null || echo "")

# 4) 헤더/JSON 일치성 검증
if [ -z "$build_sha_header" ] && [ -z "$build_sha_json" ]; then
  echo "[FAIL] buildSha missing in both header and JSON"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

if [ -n "$build_sha_header" ] && [ -n "$build_sha_json" ] && [ "$build_sha_header" != "$build_sha_json" ]; then
  echo "[FAIL] buildSha mismatch: header=$build_sha_header, json=$build_sha_json"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

build_sha="${build_sha_json:-${build_sha_header}}"

# 5) 40-hex 검증
if [ -z "$build_sha" ] || [ "$build_sha" = "unknown" ]; then
  echo "[FAIL] buildSha is missing or unknown"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

if [ ${#build_sha} -ne 40 ]; then
  echo "[FAIL] buildSha length is ${#build_sha} (expected 40)"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

if ! echo "$build_sha" | grep -qE '^[0-9a-f]{40}$'; then
  echo "[FAIL] buildSha is not 40-hex: $build_sha"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

# 6) HEAD 일치 확인 (dev 환경 기준)
git_head=$(git rev-parse HEAD 2>/dev/null || echo "")

if [ -z "$git_head" ]; then
  echo "[FAIL] git rev-parse HEAD failed"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

if [ "$build_sha" != "$git_head" ]; then
  echo "[FAIL] buildSha mismatch: healthz=$build_sha, git HEAD=$git_head"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

# ✅ 성공: 표준 출력 1줄만
git_head_short=$(echo "$git_head" | cut -c1-7)
echo "OK: buildSha matches HEAD($git_head_short)"

rm -f "$TMP_HDR" "$TMP_BODY"
exit 0

