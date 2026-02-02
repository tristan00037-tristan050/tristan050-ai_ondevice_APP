#!/usr/bin/env bash
set -euo pipefail

DOC="docs/ops/SEALED_RECORDS/2026-02-01_M7_SEALED.md"

M7_SEALED_RECORD_PRESENT_OK=0
M7_SEALED_RECORD_FORMAT_OK=0
M7_SEALED_RECORD_NO_PLACEHOLDER_OK=0

# 1) 존재/비어있지 않음
test -s "$DOC" || { echo "BLOCK: missing/empty $DOC"; exit 1; }
M7_SEALED_RECORD_PRESENT_OK=1

# 2) placeholder 금지
if grep -nE '(TODO|TBD|PLACEHOLDER|FIXME)' "$DOC" >/dev/null; then
  echo "BLOCK: placeholder detected"
  grep -nE '(TODO|TBD|PLACEHOLDER|FIXME)' "$DOC" | head -n 20
  exit 1
fi
M7_SEALED_RECORD_NO_PLACEHOLDER_OK=1

# 3) 필수 토큰(앵커/PR/DoD 키 섹션)
REQ=(
  "verify_repo_contracts.sh"
  "EXIT=0"
  "#293" "#294" "#295" "#296"
  "DoD Keys"
)
for tok in "${REQ[@]}"; do
  grep -qF "$tok" "$DOC" || { echo "BLOCK: missing token: $tok"; exit 1; }
done
M7_SEALED_RECORD_FORMAT_OK=1

echo "M7_SEALED_RECORD_PRESENT_OK=$M7_SEALED_RECORD_PRESENT_OK"
echo "M7_SEALED_RECORD_FORMAT_OK=$M7_SEALED_RECORD_FORMAT_OK"
echo "M7_SEALED_RECORD_NO_PLACEHOLDER_OK=$M7_SEALED_RECORD_NO_PLACEHOLDER_OK"

