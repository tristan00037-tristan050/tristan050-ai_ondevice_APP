#!/usr/bin/env bash
# Proof 내용은 유지하고, freshness 가드용 날짜(ts_utc)만 오늘(UTC)로 갱신. ts_utc= 없으면/갱신 실패면 fail-closed.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
LATEST="docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md"
[[ -s "$LATEST" ]] || { echo "BLOCK: missing/empty $LATEST"; exit 1; }

# 1) ts_utc= 라인이 없으면 즉시 실패(침묵 성공 방지)
if ! grep -qE '^ts_utc=' "$LATEST"; then
  echo "BLOCK: ts_utc marker missing"
  exit 1
fi

TODAY_UTC="$(date -u +%Y-%m-%dT00:00:00Z)"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

# 2) 치환 수행
sed -E "s/^ts_utc=.*/ts_utc=${TODAY_UTC}/" "$LATEST" > "$TMP"
mv "$TMP" "$LATEST"

# 3) 치환 결과 확인(정확히 오늘 값이 반영됐는지)
if ! grep -qE "^ts_utc=${TODAY_UTC}$" "$LATEST"; then
  echo "BLOCK: ts_utc not updated"
  exit 1
fi

echo "OK: ts_utc updated to ${TODAY_UTC}"
