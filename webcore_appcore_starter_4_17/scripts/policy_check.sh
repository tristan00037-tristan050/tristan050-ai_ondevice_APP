#!/usr/bin/env bash
set -euo pipefail

FAIL=0

echo "[policy] Checking hardcoded BFF URLs in app code..."
# 허용: os/bff.ts (OS 공통 모듈의 기본값), 주석, 테스트 파일
# rg 출력 형식: "파일경로:줄번호:내용"
VIOLATIONS=$(rg -n 'http://(localhost|127\.0\.0\.1):8081' packages/app-expo/src \
  | rg -v 'packages/app-expo/src/os/bff\.ts' \
  | rg -v '__tests__|\.test\.|\.spec\.' \
  | while IFS=: read -r file line content; do
      # 주석 라인 제외 (/*, */, *, //, #)
      if echo "$content" | rg -q '^\s*[/*#]' || echo "$content" | rg -q '^\s*\*'; then
        continue
      fi
      echo "$file:$line:$content"
    done)

if [ -n "$VIOLATIONS" ]; then
  echo "[policy] ERROR: hardcoded BFF URL found in packages/app-expo/src"
  echo "$VIOLATIONS"
  echo "[policy] Use resolveBffBaseUrl() from packages/app-expo/src/os/bff.ts instead"
  FAIL=1
fi

echo
echo "[policy] Checking direct X-* header construction in app code..."
# tenantHeaders.ts 자체는 허용
if rg -n '"X-Tenant"|"X-User-Id"|"X-User-Role"' packages/app-expo/src \
  | rg -v 'packages/app-expo/src/os/tenantHeaders\.ts'; then
  echo "[policy] ERROR: direct tenant headers found. Use tenantHeaders()"
  FAIL=1
fi

echo
if [ "${FAIL}" -ne 0 ]; then
  echo "[policy] FAILED"
  exit 1
fi

echo "[policy] OK"

