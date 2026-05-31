#!/usr/bin/env bash
# PR-D security gate — connect_loop Chat UI Bridge 소스 정적 검사.
# storage 0 / non-local 0 / token 0 / claim 0 을 강제한다(하나라도 위반 시 non-zero exit).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/butler-desktop/src"

FILES=$(find "$SRC/lib/connect_loop" "$SRC/components/connect_loop" -type f \( -name '*.ts' -o -name '*.tsx' \) 2>/dev/null)
if [ -z "$FILES" ]; then
  echo "[FAIL] connect_loop 소스 파일을 찾지 못함: $SRC"
  exit 2
fi

fail=0
report() {  # label, matched-lines
  local label="$1" hits="$2" count
  count=$(printf '%s' "$hits" | grep -c . || true)
  if [ "$count" -ne 0 ]; then
    # Codex P2: verdict-only — 매칭된 소스 라인(민감 문자열 가능)을 CI 출력에 echo 하지 않는다.
    echo "[FAIL] $label: $count (verdict-only; 위치는 로컬에서 grep 으로 확인)"
    fail=1
  else
    echo "[ OK ] $label: 0"
  fi
}

# Codex P1: verdict-only (AGENTS.md). 스캔 대상 파일 목록 등 비-verdict 출력은 하지 않는다.
echo "=== PR-D security gate (connect_loop source) ==="

# 1) storage 0 — 영속 브라우저 스토리지 금지
report "storage" "$(grep -nE 'localStorage|sessionStorage|indexedDB' $FILES 2>/dev/null || true)"

# 2) non-local 0 — 비로컬 네트워크 primitive / 비로컬 URL 금지
#    (로컬 sidecar 경계: http://127.0.0.1:8765 만 허용)
net_prim=$(grep -nE 'fetch[[:space:]]*\(|axios\.|XMLHttpRequest|sendBeacon|WebSocket' $FILES 2>/dev/null || true)
non_local_url=$(grep -noE 'https?://[^"'"'"'`) ]+' $FILES 2>/dev/null | grep -v '127\.0\.0\.1:8765' || true)
non_local_all=$(printf '%s\n%s' "$net_prim" "$non_local_url" | grep -c . >/dev/null; printf '%s\n%s' "$net_prim" "$non_local_url" | sed '/^$/d')
report "non-local" "$non_local_all"

# 3) token 0 — 토큰 노출/로깅 금지
report "token" "$(grep -nE '(localStorage|sessionStorage)[^;]*[Tt]oken|console\.[a-z]+\([^)]*[Tt]oken' $FILES 2>/dev/null || true)"

# 4) claim 0 — 운영/출시/상용 보증 문구 금지
report "claim" "$(grep -niE 'production[- ]ready|상용|출시 완료|릴리스 완료|정식 출시|GA 릴리스|배포 승인됨' $FILES 2>/dev/null || true)"

echo
if [ "$fail" -ne 0 ]; then
  echo "RESULT: FAIL (위반 발견)"
  exit 1
fi
echo "RESULT: PASS — storage 0 / non-local 0 / token 0 / claim 0"
