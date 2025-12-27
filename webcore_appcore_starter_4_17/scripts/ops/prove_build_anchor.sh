#!/usr/bin/env bash
set -euo pipefail

# ✅ E) 증빙 자동화: build anchor 증빙을 1회 실행으로 생성/갱신
# 역할: dev_bff restart → verify_build_anchor 실행 → 증빙 로그 생성 + .latest 갱신까지 1회로 끝냄

ROOT="$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"
cd "$ROOT"

TS="$(date -u +%Y%m%d-%H%M%S)"
PROOF_DIR="$ROOT/docs/ops"
mkdir -p "$PROOF_DIR"

PROOF_LOG="$PROOF_DIR/r10-s7-build-anchor-esm-proof-$TS.log"
LATEST="$PROOF_DIR/r10-s7-build-anchor-esm-proof.latest"

# 증빙 로그 시작
{
  echo "[proof] R10-S7 Build Anchor ESM Proof"
  echo "Generated: $TS"
  echo "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
  echo ""
  
  # 1) 표준 빌드 (workspace 표준)
  echo "=== Step 1: Standard Build ==="
  npm ci 2>&1 | tail -5 || {
    echo "[FAIL] npm ci failed"
    exit 1
  }
  npm run build --workspace=@appcore/bff-accounting 2>&1 | tail -10 || {
    echo "[FAIL] build failed"
    exit 1
  }
  echo ""
  
  # 2) BFF 재시작
  echo "=== Step 2: BFF Restart ==="
  ./scripts/dev_bff.sh restart 2>&1 | head -20 || {
    echo "[FAIL] BFF restart failed"
    exit 1
  }
  echo ""
  
  # 3) build_info.json 확인
  echo "=== Step 3: build_info.json ==="
  BUILD_INFO="$ROOT/packages/bff-accounting/dist/build_info.json"
  if [ -f "$BUILD_INFO" ]; then
    head -10 "$BUILD_INFO"
  else
    echo "[FAIL] build_info.json not found"
    exit 1
  fi
  echo ""
  
  # 4) healthz 헤더 확인 (메타만, 본문 덤프 금지)
  echo "=== Step 4: healthz Headers ==="
  curl -iS --max-time 3 http://127.0.0.1:8081/healthz 2>&1 | grep -E "HTTP|X-OS-Build" | head -5
  echo ""
  
  # 5) healthz JSON 확인 (메타만)
  echo "=== Step 5: healthz JSON ==="
  curl -sS --max-time 3 http://127.0.0.1:8081/healthz 2>&1 | jq '{buildSha, buildShaShort, buildTime}' 2>/dev/null || echo "healthz not available"
  echo ""
  
  # 6) HEAD 확인
  echo "=== Step 6: Git HEAD ==="
  echo "HEAD=$(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
  echo ""
  
  # 7) 검증 실행
  echo "=== Step 7: Verification ==="
  bash "$ROOT/scripts/ops/verify_build_anchor.sh" || {
    echo "[FAIL] Verification failed"
    exit 1
  }
  
} > "$PROOF_LOG" 2>&1

# .latest 포인터 갱신
echo "$(basename "$PROOF_LOG")" > "$LATEST"

echo "[OK] Proof generated: $PROOF_LOG"
echo "[OK] Latest pointer: $LATEST"
cat "$PROOF_LOG"

