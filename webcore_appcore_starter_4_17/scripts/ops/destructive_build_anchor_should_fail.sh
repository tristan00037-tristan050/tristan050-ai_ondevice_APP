#!/usr/bin/env bash
set -euo pipefail

# ✅ R10-S7 ESM Build Anchor "재발 0 잠금" 정본 v1.0
# 파괴 테스트 정본: 항상 재현 가능한 FAIL

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"
BI="packages/bff-accounting/dist/build_info.json"
BI_BAK="${BI}.bak"

fail() { echo "FAIL: $*"; exit 1; }

test -f "$BI" || fail "missing $BI"

cp "$BI" "$BI_BAK"
cleanup() {
  [[ -f "$BI_BAK" ]] && mv "$BI_BAK" "$BI"
}
trap cleanup EXIT

# 40-hex이지만 HEAD와 불일치하도록 오염 (결정적)
node --input-type=module -e '
import fs from "node:fs";
const p = "packages/bff-accounting/dist/build_info.json";
const j = JSON.parse(fs.readFileSync(p,"utf8"));
j.buildSha = "0000000000000000000000000000000000000000";
fs.writeFileSync(p, JSON.stringify(j, null, 2) + "\n");
'

# 재기동(변조 반영) + 대기/헬스 안정화는 dev_bff.sh가 담당
./scripts/dev_bff.sh restart

# 변조 상태: verify는 반드시 FAIL
set +e
OUT="$(BASE_URL="$BASE_URL" bash scripts/ops/verify_build_anchor.sh 2>&1)"
EC=$?
set -e

if [[ "$EC" -eq 0 ]]; then
  echo "$OUT" | sed -n '1,40p' || true
  fail "destructive expected FAIL, but verify passed"
fi

# 원복 + 재기동 + PASS 복귀까지 확인(표준 루틴)
mv "$BI_BAK" "$BI"
trap - EXIT

./scripts/dev_bff.sh restart
BASE_URL="$BASE_URL" bash scripts/ops/verify_build_anchor.sh >/dev/null

echo "PASS: tamper -> verify failed (exit=$EC), restore -> verify passed"

