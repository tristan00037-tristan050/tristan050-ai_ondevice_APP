#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/webcore_appcore_starter_4_17"

BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"

ts="$(date +%Y%m%d-%H%M%S)"
ymd="${ts%%-*}"

mkdir -p docs/ops
log="docs/ops/r10-s7-build-anchor-esm-proof-${ts}.log"
latest="docs/ops/r10-s7-build-anchor-esm-proof.latest"

{
  echo "== PROOF START $(date -Is) =="
  echo "PWD=$(pwd)"
  echo "HEAD=$(git rev-parse HEAD)"

  echo
  echo "== npm ci =="
  npm ci

  echo
  echo "== build workspace =="
  npm run build --workspace=@appcore/bff-accounting

  echo
  echo "== restart BFF =="
  ./scripts/dev_bff.sh restart

  echo
  echo "== verify_build_anchor =="
  BASE_URL="$BASE_URL" bash scripts/ops/verify_build_anchor.sh

  echo
  echo "== dist/build_info.json (top 80) =="
  sed -n '1,80p' packages/bff-accounting/dist/build_info.json || true

  echo
  echo "== /healthz (top 80) =="
  curl -iS --connect-timeout 2 --max-time 3 "${BASE_URL%/}/healthz" | sed -n '1,80p'

  echo
  echo "== PROOF END $(date -Is) =="
} > "$log"

# .latest 갱신
printf "%s\n" "$(basename "$log")" > "$latest"

# 하루 최신 1개 유지(중복 제거): 동일 ymd의 과거 로그는 삭제
# (git-tracked일 수 있으므로 삭제는 "의도된 변경"이며 커밋 대상으로 취급)
for f in docs/ops/r10-s7-build-anchor-esm-proof-"$ymd"-*.log; do
  [[ "$f" == "$log" ]] && continue
  [[ -f "$f" ]] && rm -f "$f"
done

echo "OK: wrote $log"
echo "OK: updated $latest -> $(cat "$latest")"
