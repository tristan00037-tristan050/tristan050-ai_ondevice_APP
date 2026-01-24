#!/usr/bin/env bash
set -euo pipefail

CANONICALIZE_SHARED_SINGLE_SOURCE_OK=0

cleanup() {
  echo "CANONICALIZE_SHARED_SINGLE_SOURCE_OK=${CANONICALIZE_SHARED_SINGLE_SOURCE_OK}"
}
trap cleanup EXIT

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ALLOW_DIR="packages/common/src/canon"
[[ -d "$ALLOW_DIR" ]] || { echo "FAIL: missing $ALLOW_DIR"; exit 1; }

have_rg() { command -v rg >/dev/null 2>&1; }

# canonicalizeJson 함수 구현(키 정렬 stringify) 흔적을 탐지
# 허용: packages/common/src/canon/**
# 호출(canonicalizeJson()은 허용, 구현만 차단)
if have_rg; then
  HITS="$(rg -n --hidden --no-messages \
    --glob '!**/node_modules/**' \
    --glob '!**/dist/**' \
    --glob '!**/coverage/**' \
    -e 'function\s+canonicalizeJson\s*\(' \
    -e 'const\s+canonicalizeJson\s*=\s*' \
    -e 'export\s+function\s+canonicalizeJson\s*\(' \
    -e 'function\s+sortRec\s*\(' \
    -e 'const\s+sortRec\s*=\s*' \
    . || true)"
else
  # grep fallback (less precise but fail-closed)
  # Combine patterns with | (OR) for -E
  PAT='(function\s+canonicalizeJson\s*\(|const\s+canonicalizeJson\s*=|export\s+function\s+canonicalizeJson\s*\(|function\s+sortRec\s*\(|const\s+sortRec\s*=)'
  HITS="$(grep -RIn \
    --exclude-dir=node_modules \
    --exclude-dir=dist \
    --exclude-dir=coverage \
    -E "$PAT" \
    . 2>/dev/null || true)"
fi

# 허용 경로 외 히트만 남김 (경로 정규화)
ALLOW_PATTERN="^\./${ALLOW_DIR}/"
BAD=""
while IFS= read -r line; do
  if [[ -n "$line" ]] && ! echo "$line" | grep -qE "$ALLOW_PATTERN"; then
    if [[ -z "$BAD" ]]; then
      BAD="$line"
    else
      BAD="$BAD"$'\n'"$line"
    fi
  fi
done <<< "$HITS"

if [[ -n "$BAD" ]]; then
  echo "FAIL: canonicalization duplicate implementation detected (must be single-source)"
  echo "$BAD"
  exit 1
fi

CANONICALIZE_SHARED_SINGLE_SOURCE_OK=1
exit 0

