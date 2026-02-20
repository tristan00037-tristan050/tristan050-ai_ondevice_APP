#!/usr/bin/env bash
set -euo pipefail

ONPREM_LATEST_WHITELIST_ONLY_V2_OK=0
ONPREM_LATEST_LONG_LINE_SCAN_EOF_SAFE_OK=0

trap 'echo "ONPREM_LATEST_WHITELIST_ONLY_V2_OK=$ONPREM_LATEST_WHITELIST_ONLY_V2_OK";
      echo "ONPREM_LATEST_LONG_LINE_SCAN_EOF_SAFE_OK=$ONPREM_LATEST_LONG_LINE_SCAN_EOF_SAFE_OK"' EXIT

allowed="docs/ops/contracts/ONPREM_LATEST_ALLOWED_KEYS_V2.txt"
sensitive="docs/ops/contracts/PROOF_SENSITIVE_PATTERNS_V1.txt"
latest="docs/ops/PROOFS/ONPREM_REAL_WORLD_PROOF_LATEST.md"

test -f "$allowed" || { echo "BLOCK: missing $allowed"; exit 1; }
test -f "$sensitive" || { echo "BLOCK: missing $sensitive"; exit 1; }
test -f "$latest" || { echo "BLOCK: missing $latest"; exit 1; }

# SSOT empty => BLOCK (fail-closed)
test -s "$allowed" || { echo "BLOCK: allowed keys SSOT empty"; exit 1; }
test -s "$sensitive" || { echo "BLOCK: sensitive patterns SSOT empty"; exit 1; }

# 1) 민감 패턴 차단(SSOT 기반)
if grep -nFf "$sensitive" "$latest" >/dev/null 2>&1; then
  echo "BLOCK: sensitive pattern detected in LATEST"
  grep -nFf "$sensitive" "$latest" | head -n 10
  exit 1
fi

# 2) whitelist-only + 긴라인 차단(EOF-safe)
while IFS= read -r line || [ -n "$line" ]; do
  # 빈 줄은 허용(더 엄격히 하려면 빈 줄도 BLOCK 가능)
  [ -z "$line" ] && continue
  # 주석/헤더 줄은 검사 제외
  [[ "$line" = \#* ]] && continue
  [[ "$line" != *"="* ]] && continue

  # 2000자 이상이면 덤프/블랍으로 간주하고 차단
  if [ "${#line}" -ge 2000 ]; then
    echo "BLOCK: long line (>=2000 chars) in LATEST"
    exit 1
  fi

  # key=value 엄격 포맷(설명 문장/공백/여러 줄 흔적 차단)
  echo "$line" | grep -Eq '^[A-Za-z0-9_.-]+=[A-Za-z0-9_.:-]+$' || {
    echo "BLOCK: invalid line format in LATEST: $line"
    exit 1
  }

  key="${line%%=*}"
  grep -qx "$key" "$allowed" || {
    echo "BLOCK: key not allowed in LATEST: $key"
    exit 1
  }
done < "$latest"

ONPREM_LATEST_WHITELIST_ONLY_V2_OK=1
ONPREM_LATEST_LONG_LINE_SCAN_EOF_SAFE_OK=1
exit 0
