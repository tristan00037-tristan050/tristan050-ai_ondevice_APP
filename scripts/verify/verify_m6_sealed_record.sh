#!/usr/bin/env bash
set -euo pipefail

DOC="docs/ops/SEALED_RECORDS/2026-02-01_M6_SEALED.md"

M6_SEALED_RECORD_PRESENT_OK=0
M6_SEALED_RECORD_NO_PLACEHOLDER_OK=0
M6_SEALED_RECORD_PR_MAP_OK=0

# 1) 존재/비어있지 않음
if [[ -s "$DOC" ]]; then
  M6_SEALED_RECORD_PRESENT_OK=1
else
  echo "missing or empty: $DOC"
  exit 1
fi

# 2) placeholder/TODO 차단
if grep -nE '(TODO|TBD|PLACEHOLDER|FIXME)' "$DOC" >/dev/null; then
  echo "placeholder detected in $DOC"
  grep -nE '(TODO|TBD|PLACEHOLDER|FIXME)' "$DOC" | head -n 20
  exit 1
fi
M6_SEALED_RECORD_NO_PLACEHOLDER_OK=1

# 3) 필수 토큰(최소)
REQ=(
  "#284" "#285" "#286" "#287" "#288" "#289" "#290" "#291" "#292"
  "merged=true" "merged=false"
  "verify_repo_contracts.sh" "EXIT=0"
)
for tok in "${REQ[@]}"; do
  grep -qF "$tok" "$DOC" || { echo "missing token: $tok"; exit 1; }
done
M6_SEALED_RECORD_PR_MAP_OK=1

echo "M6_SEALED_RECORD_PRESENT_OK=$M6_SEALED_RECORD_PRESENT_OK"
echo "M6_SEALED_RECORD_NO_PLACEHOLDER_OK=$M6_SEALED_RECORD_NO_PLACEHOLDER_OK"
echo "M6_SEALED_RECORD_PR_MAP_OK=$M6_SEALED_RECORD_PR_MAP_OK"

