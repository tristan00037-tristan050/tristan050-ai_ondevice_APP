#!/usr/bin/env bash
set -euo pipefail

# ✅ B) zsh parse error 재발 0: 복잡한 검증은 scripts/ops/*.sh로만 제공
# 역할: build anchor 무결성 검증 (헤더/JSON 분리 + fail-fast)
# 출력 표준: 성공 시 `OK: buildSha matches HEAD(<short>)`
# 실패 시: 원인 1줄 + exit 1 (PASS 요약 금지)

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

PORT="${PORT:-8081}"
HEALTHZ="http://127.0.0.1:${PORT}/healthz"

# 1) healthz 200 확인
TMP_HDR="$(mktemp -t verify_anchor_hdr.XXXXXX)"
TMP_BODY="$(mktemp -t verify_anchor_body.XXXXXX)"

code=$(curl -fsSI --max-time 3 "$HEALTHZ" -D "$TMP_HDR" -o "$TMP_BODY" 2>/dev/null || echo "000")

if [ "$code" != "200" ]; then
  echo "[FAIL] healthz returned $code (expected 200)"
  rm -f "$TMP_HDR" "$TMP_BODY"
  exit 1
fi

# 2) 헤더 buildSha 추출 (완전 분리)
build_sha_header=$(grep -i "^x-os-build-sha:" "$TMP_HDR" 2>/dev/null | cut -d' ' -f2- | tr -d '\r' | head -1 || echo "")

# 3) JSON buildSha 추출 (완전 분리)
build_sha_json=$(curl -fsS --max-time 3 "$HEALTHZ" 2>/dev/null | jq -r '.buildSha // empty' 2>/dev/null || echo "")

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

