#!/usr/bin/env bash
set -euo pipefail

# ✅ R10-S7 ESM Build Anchor "재발 0 잠금" 정본 v1.0
# 결정적 판정자: Header SHA == JSON SHA == git HEAD

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"
URL="${BASE_URL%/}/healthz"
SHA_RE='^[0-9a-fA-F]{40}$'

fail() { echo "FAIL: $*"; exit 1; }

# ESM 순수성 회귀 차단: dist require( 0
if rg -n "require\\(" packages/bff-accounting/dist >/dev/null 2>&1; then
  rg -n "require\\(" packages/bff-accounting/dist || true
  fail "dist contains require( (ESM regression)"
fi

# Header (분리)
hdr="$(curl -fsSI --connect-timeout 2 --max-time 3 "$URL")" || fail "healthz header fetch failed"
sha_hdr="$(printf "%s" "$hdr" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-os-build-sha"{print $2}' | tail -n 1)"

[[ -n "${sha_hdr:-}" ]] || fail "missing X-OS-Build-SHA header"
[[ "$sha_hdr" =~ $SHA_RE ]] || fail "invalid header sha: $sha_hdr"

# Body (분리)
body="$(curl -fsS --connect-timeout 2 --max-time 3 "$URL")" || fail "healthz body fetch failed"

sha_json="$(
  printf "%s" "$body" | node --input-type=module -e '
let d=""; process.stdin.setEncoding("utf8");
process.stdin.on("data", c => d += c);
process.stdin.on("end", () => {
  try { const j = JSON.parse(d); process.stdout.write(String(j.buildSha||"").trim()); }
  catch { process.stdout.write(""); }
});'
)"

[[ -n "${sha_json:-}" ]] || fail "missing JSON buildSha"
[[ "$sha_json" =~ $SHA_RE ]] || fail "invalid json sha: $sha_json"
[[ "$sha_hdr" == "$sha_json" ]] || fail "header sha != json sha ($sha_hdr != $sha_json)"

head_sha="$(git rev-parse HEAD)"
[[ "$head_sha" == "$sha_hdr" ]] || fail "git HEAD != healthz sha ($head_sha != $sha_hdr)"

echo "OK: buildSha matches HEAD(${head_sha:0:7})"
