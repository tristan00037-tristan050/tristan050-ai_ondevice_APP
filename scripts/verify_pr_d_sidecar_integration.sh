#!/usr/bin/env bash
# PR-D sidecar integration 보안 게이트 (maindev v1.2 이식, 코덱스 구현 기준).
# connect_loop 소스에 한정해 스캔한다(전체 src 스캔은 무관 기능의 fetch 등에 오탐).
# 위반 시 verdict-only(BLOCK 코드)로 non-zero exit.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# connect_loop 스캔 대상(프론트 + 파이썬)
CL_TS_DIRS=(
  "butler-desktop/src/lib/connect_loop"
  "butler-desktop/src/components/connect_loop"
  "butler-desktop/src/__tests__/connect_loop"
)
CL_TS_FILES=("butler-desktop/src/__tests__/ConnectLoopChatUIBridge.test.tsx")
CL_PY=("butler_pc_core/connect_loop" "butler_pc_core/sidecar/routes/router_decide.py" "tests/connect_loop")
TS_TARGETS=()
for p in "${CL_TS_DIRS[@]}" "${CL_TS_FILES[@]}"; do [ -e "$p" ] && TS_TARGETS+=("$p"); done

fail=0
gate() {  # label, grep-output
  local label="$1" hits="$2" n
  n=$(printf '%s' "$hits" | grep -c . || true)
  if [ "$n" -ne 0 ]; then echo "[FAIL] $label: $n"; fail=1; else echo "[ OK ] $label: 0"; fi
}

echo "=== PR-D sidecar integration security gate (connect_loop scope) ==="

# 계약/SSOT 미변경
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  contract=$(git diff --name-only origin/main...HEAD 2>/dev/null | grep -E "^schemas/connect_loop/|^docs/ssot/connect_loop/" || true)
  gate "contract_ssot_unmodified" "$contract"
fi

# storage 0
gate "storage" "$(grep -RInE 'localStorage|sessionStorage|indexedDB' "${TS_TARGETS[@]}" 2>/dev/null || true)"

# non-local 0 (로컬 sidecar 경계 외 네트워크 primitive / 비로컬 URL)
# 런타임 소스(lib/components)만 스캔한다. __tests__ 는 비로컬 거부를 검증하는 negative 픽스처
# (example.invalid, localhost 등)를 의도적으로 포함하므로 제외(오탐 방지).
RUNTIME_TS=()
for p in "butler-desktop/src/lib/connect_loop" "butler-desktop/src/components/connect_loop"; do [ -e "$p" ] && RUNTIME_TS+=("$p"); done
nonlocal=$(grep -RInE 'fetch[[:space:]]*\(|axios\.|XMLHttpRequest|sendBeacon|WebSocket' "${RUNTIME_TS[@]}" 2>/dev/null | grep -v '127\.0\.0\.1:8765' || true)
nonlocal_url=$(grep -RnoE 'https?://[^"'"'"'`) ]+' "${RUNTIME_TS[@]}" 2>/dev/null | grep -v '127\.0\.0\.1:8765' || true)
gate "non-local(runtime)" "$(printf '%s\n%s' "$nonlocal" "$nonlocal_url" | sed '/^$/d')"

# token 0 (스토리지/로그 노출)
gate "token" "$(grep -RInE '(localStorage|sessionStorage)[^;]*[Tt]oken|console\.[a-z]+\([^)]*[Tt]oken' "${TS_TARGETS[@]}" 2>/dev/null || true)"

# claim 0
gate "claim" "$(grep -RInE 'production[- ]ready|APPROVED_FOR_PRODUCTION|production_claim_allowed|release_claim_allowed|상용 출시|정식 출시' "${TS_TARGETS[@]}" "${CL_PY[@]}" 2>/dev/null || true)"

# router_decide.py 외부 전송 0
gate "router_decide_no_external_send" "$(grep -InE 'requests\.|httpx\.|aiohttp\.|urllib|socket\.create_connection' butler_pc_core/sidecar/routes/router_decide.py 2>/dev/null || true)"

# binary 0 (staged)
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  gate "binary" "$(git diff --cached --name-only 2>/dev/null | grep -E '\.(safetensors|gguf|bin|npy|pkl)$' || true)"
fi

echo
if [ "$fail" -ne 0 ]; then echo "RESULT: FAIL"; exit 1; fi
echo "RESULT: PASS — contract/ssot·storage·non-local·token·claim·router-external·binary 0"
