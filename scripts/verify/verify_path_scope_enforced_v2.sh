#!/usr/bin/env bash
set -euo pipefail

PATH_SCOPE_ENFORCED_V2_OK=0

trap 'echo "PATH_SCOPE_ENFORCED_V2_OK=${PATH_SCOPE_ENFORCED_V2_OK}"' EXIT

# SSOT 파일(기존 P4-P1-03에서 이미 존재)
ssot="docs/ops/contracts/PATH_SCOPE_SSOT_V1.json"
test -f "$ssot" || { echo "BLOCK: missing PATH_SCOPE SSOT ($ssot)"; exit 1; }

# 스캐너 성격의 verify 스크립트를 넓게 탐지 (bash 3.x 호환: mapfile 대신 while read)
scanners=()
while IFS= read -r line; do
  [[ -n "$line" ]] && scanners+=("$line")
done < <(find scripts/verify -maxdepth 1 -type f -name 'verify_*' 2>/dev/null | grep -E 'path_scope|path-scope' || true)

# 최소 1개라도 있으면, 전부 SSOT 참조를 강제
# SSOT 참조 기준: 파일 내용에 PATH_SCOPE_SSOT_V1 문자열이 포함되어 있어야 함
for f in "${scanners[@]}"; do
  # 본인 스크립트는 제외
  [[ "$f" == "scripts/verify/verify_path_scope_enforced_v2.sh" ]] && continue

  if ! grep -q "PATH_SCOPE_SSOT_V1" "$f"; then
    echo "BLOCK: scanner verify does not reference PATH_SCOPE SSOT: $f"
    exit 1
  fi
done

PATH_SCOPE_ENFORCED_V2_OK=1
exit 0
