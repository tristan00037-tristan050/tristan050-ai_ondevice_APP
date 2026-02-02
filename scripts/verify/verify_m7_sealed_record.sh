#!/usr/bin/env bash
set -euo pipefail

DOC="docs/ops/SEALED_RECORDS/2026-02-01_M7_SEALED.md"

M7_SEALED_RECORD_PRESENT_OK=0
M7_SEALED_RECORD_FORMAT_OK=0
M7_SEALED_RECORD_NO_PLACEHOLDER_OK=0

# 1) 존재/비어있지 않음
test -s "$DOC" || { echo "BLOCK: missing/empty $DOC"; exit 1; }
M7_SEALED_RECORD_PRESENT_OK=1

# 2) placeholder 금지 (규율 설명 제외: "PLACEHOLDER 금지" 같은 설명 텍스트는 허용)
if grep -nE '(TODO|TBD|FIXME)' "$DOC" >/dev/null; then
  echo "BLOCK: placeholder detected"
  grep -nE '(TODO|TBD|FIXME)' "$DOC" | head -n 20
  exit 1
fi
# PLACEHOLDER는 규율 설명 또는 DoD 키 이름에만 사용 가능 (실제 placeholder는 금지)
# 허용: "PLACEHOLDER 금지" (규율 설명), "_PLACEHOLDER_OK=1" (DoD 키 이름)
# 금지 패턴과 함께 나오는 PLACEHOLDER는 제외
BAD_PLACEHOLDER="$(grep -nE 'PLACEHOLDER' "$DOC" | grep -vE '(금지|_OK=|forbidden|prohibited)' || true)"
if [[ -n "$BAD_PLACEHOLDER" ]]; then
  echo "BLOCK: placeholder detected (not in rule description or DoD key)"
  echo "$BAD_PLACEHOLDER" | head -n 20
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

