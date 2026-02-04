#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

# 이식성 확보: macOS/BSD date, GNU date 모두 동작하는 함수
iso_utc_now() {
  # macOS/BSD date, GNU date 모두 동작하는 ISO-8601 UTC 타임스탬프
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

ts_compact() {
  # 파일명용 타임스탬프 (이식성 OK)
  date -u +"%Y%m%d-%H%M%S"
}

BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"
BI="packages/bff-accounting/dist/build_info.json"
BI_BAK="${BI}.bak"

fail() { echo "FAIL: $*"; exit 1; }

test -f "$BI" || fail "missing $BI"

# === 준비: 현재 verify PASS 확인 (정상 상태) ===
echo "[destructive] Step 1: Verify initial state (should PASS)..."
BASE_URL="$BASE_URL" bash scripts/ops/verify_build_anchor.sh || fail "initial verify failed (expected PASS)"

# === 변조: buildSha를 40-hex이지만 HEAD와 다른 값으로 교체 ===
echo "[destructive] Step 2: Tampering build_info.json (40-hex but != HEAD)..."
cp "$BI" "$BI_BAK"
cleanup() {
  [[ -f "$BI_BAK" ]] && mv "$BI_BAK" "$BI"
}
trap cleanup EXIT

# HEAD의 마지막 1글자를 다른 hex로 바꿔서 결정적으로 불일치 생성
HEAD_SHA="$(git rev-parse HEAD)"
TAMPERED_SHA="${HEAD_SHA:0:39}1"  # 마지막 글자를 '1'로 변경 (원래가 '1'이면 '0'으로)

node --input-type=module -e '
import fs from "node:fs";
const p = "packages/bff-accounting/dist/build_info.json";
const j = JSON.parse(fs.readFileSync(p,"utf8"));
j.buildSha = process.argv[1];
fs.writeFileSync(p, JSON.stringify(j, null, 2) + "\n");
' "$TAMPERED_SHA"

echo "[destructive] Tampered buildSha: $TAMPERED_SHA (HEAD: $HEAD_SHA)"

# === 재기동: DEV_BFF_SKIP_BUILD=1로 덮어쓰기 방지 ===
echo "[destructive] Step 3: Restart BFF with SKIP_BUILD=1 (preserve tampered build_info)..."
# dev_bff.sh는 buildSha 불일치로 exit 1하지만, 이는 예상된 동작이므로 무시하고 계속 진행
set +e
DEV_BFF_SKIP_BUILD=1 ./scripts/dev_bff.sh restart 2>&1 | grep -v "FAIL: buildSha mismatch" || true
set -e

# BFF가 실제로 기동되었는지 확인 (healthz 폴링)
echo "[destructive] Waiting for BFF to be ready (may have buildSha mismatch warning)..."
for i in $(seq 1 30); do
  if curl -fsS --max-time 2 "$BASE_URL/healthz" >/dev/null 2>&1; then
    echo "[destructive] BFF is ready"
    break
  fi
  sleep 1
  if [ $i -eq 30 ]; then
    fail "BFF did not become ready after 30s"
  fi
done

# === 검증: 변조 상태에서 verify는 반드시 FAIL ===
echo "[destructive] Step 4: Verify tampered state (should FAIL)..."
set +e
OUT="$(BASE_URL="$BASE_URL" bash scripts/ops/verify_build_anchor.sh 2>&1)"
EC=$?
set -e

if [[ "$EC" -eq 0 ]]; then
  echo "$OUT" | sed -n '1,40p' || true
  fail "destructive expected FAIL, but verify passed (tampered buildSha should not match HEAD)"
fi

echo "[destructive] ✓ Tampered state correctly failed (exit=$EC)"

# === 원복: 원래 build_info.json 복구 ===
echo "[destructive] Step 5: Restore original build_info.json..."
mv "$BI_BAK" "$BI"
trap - EXIT

# === 재기동: 다시 DEV_BFF_SKIP_BUILD=1로 원복 반영 ===
echo "[destructive] Step 6: Restart BFF with SKIP_BUILD=1 (restored build_info)..."
# 원복 후에는 buildSha가 일치하므로 정상적으로 PASS해야 함
DEV_BFF_SKIP_BUILD=1 ./scripts/dev_bff.sh restart

# === 검증: 원복 후 verify는 반드시 PASS ===
echo "[destructive] Step 7: Verify restored state (should PASS)..."
BASE_URL="$BASE_URL" bash scripts/ops/verify_build_anchor.sh || fail "restored verify failed (expected PASS)"

echo "[destructive] PASS: tamper -> verify failed (exit=$EC), restore -> verify passed"

